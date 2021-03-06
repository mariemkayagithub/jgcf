import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup as bs
from pymongo import MongoClient

from init import logger_init, config_init
from utility import request_site_page, format_date, remove_special_char, get_content_text, table_to_list

# 天津市税务局
# http://wzcx.tjsat.gov.cn/sgscx_showlistcf.action
# http://wzcx.tjsat.gov.cn/cx_zdwfaj.action?szsf=11200000000
first_url = 'http://wzcx.tjsat.gov.cn/sgscx_showlistcf.action'
second_url = 'http://wzcx.tjsat.gov.cn/cx_cxqyxx.action'
second_url_arti = 'http://wzcx.tjsat.gov.cn/cx_getQyxx.action'
gov_name = '天津市税务局'
collection_name = 'tax_data'

logger = logger_init(gov_name)
config = config_init()
if config['mongodb']['dev_mongo'] == '1':
    db = MongoClient(config['mongodb']['ali_mongodb_url'], username=config['mongodb']['ali_mongodb_username'],
                     password=config['mongodb']['ali_mongodb_password'],
                     port=int(config['mongodb']['ali_mongodb_port']))[config['mongodb']['ali_mongodb_name']]
else:
    db = MongoClient(
        host=config['mongodb']['mongodb_host'],
        port=int(config['mongodb']['mongodb_port']),
        username=None if config['mongodb']['mongodb_username'] == '' else config['mongodb']['mongodb_username'],
        password=None if config['mongodb']['mongodb_password'] == '' else config['mongodb']['mongodb_password'])[
        config['mongodb']['mongodb_db_name']]

db[collection_name].create_index([('url', 1)])
data1 = {
    'pageCount': 68,
    'pageNum': 1
}
data2 = {
    'szsf': 11200000000,
    'fjdm': 11200000000,
    'pageCount': 33,
    'page': 1
}

data2_for_arti = {'id': '8a8080486a6df9a7016b0bdfae403365'}


def crawler():
    result_list = []
    response = request_site_page(first_url, methods='post', params=data1)
    response.encoding = response.apparent_encoding
    stop_flag = False
    if response is None:
        logger.error('网页请求错误{}'.format(first_url))
    soup = bs(response.content if response else '', 'lxml')

    if db.crawler.find({'url': first_url}).count() > 0:
        last_updated_url = db.crawler.find_one({'url': first_url})['last_updated']
    else:
        last_updated_url = ''

    while data1['pageNum'] <= data1['pageCount']:
        logger.info('第%d页' % data1['pageNum'])
        try:
            info_list = soup.body.find('table').find_all('tr')
            del(info_list[0])
            for index, each_info in enumerate(info_list):
                if each_info.text.strip() == '':    # 跳过结尾后面部分
                    break
                href = each_info.find('a')['href']
                anc_url = urljoin(first_url, href)

                if anc_url == last_updated_url:
                    stop_flag = True
                    logger.info('到达上次爬取的链接')
                    break
                if index == 0 and data1['pageNum'] == 1:
                    if db.crawler.find({'url': first_url}).count() > 0:
                        if db.crawler.find_one({'url': first_url})['last_updated'] != anc_url:
                            db.crawler.update_one({'url': first_url}, {'$set': {'last_updated': anc_url}})
                    else:
                        db.crawler.insert_one(
                            {'url': first_url, 'last_updated': anc_url, 'origin': gov_name})
                publish_date = each_info.find_all('td')[-1].text.strip()
                title = each_info.find('a').text.strip()

                if db[collection_name].count_documents({'url': anc_url}) == 0:
                    info = {
                        'title': title,
                        'publishDate': publish_date,
                        'url': anc_url,
                        'type': '行政处罚决定',
                        'origin': gov_name,
                        'status': 'not parsed'
                    }
                    logger.info('{} 新公告：{} url: {}'.format(gov_name, info['title'], anc_url))
                    if info not in result_list:
                        result_list.append(info)
                else:
                    if config['crawler_update_type']['update_type'] == '0':
                        break
            if stop_flag:
                logger.info('到达上次爬取的链接')
                break
            data1['pageNum'] += 1
            response = request_site_page(first_url, methods='post', params=data1)
            response.encoding = response.apparent_encoding
            soup = bs(response.content if response else '', 'lxml')
        except Exception as e:
            logger.error(e)
            logger.warning('提取公告url出现问题')
            continue

    response = request_site_page(second_url, params=data2, methods='post')
    response.encoding = response.apparent_encoding
    if response is None:
        logger.error('网页请求错误{}'.format(first_url))
    soup = bs(response.content if response else '', 'lxml')

    if db.crawler.find({'url': second_url}).count() > 0:
        last_updated_url = db.crawler.find_one({'url': second_url})['last_updated']
    else:
        last_updated_url = ''
    stop_flag = False
    page_count = 33
    page_num = 1
    while page_num <= page_count:
        logger.info('第%d页' % page_num)
        tr_list = soup.find('table', class_='table-update').find_all('tr')
        del (tr_list[0])
        del(tr_list[len(tr_list)-1])
        for index, each_tr in enumerate(tr_list):
            try:
                ## 信息直接显示在网页上，直接post把网页内容存下来 ##
                id = each_tr.find('td', class_='t03')['id']
                data2_for_arti['id'] = id
                inner_response = request_site_page(second_url_arti, params=data2_for_arti, methods='post')
                inner_response.encoding = inner_response.apparent_encoding
                title = each_tr.find(attrs={"class": "t03"}).text.strip()
                publish_date = each_tr.find_all('td')[-1].text.strip()
                soup = bs(inner_response.text, 'lxml')
                anc_url = get_content_text(soup.find_all('td', bgcolor="#cbddee")[-1])# 信息在当前页面中显示，无特定的url，直接存公告的网页源码
                if title + publish_date == last_updated_url:
                    stop_flag = True
                    logger.info('到达上次爬取的链接')
                    break
                if index == 0 and page_num == 1:
                    if db.crawler.find({'url': second_url}).count() > 0:
                        if db.crawler.find_one({'url': second_url})['last_updated'] != title + publish_date:
                            db.crawler.update_one({'url': second_url},
                                                  {'$set': {'last_updated': title + publish_date}})
                    else:
                        db.crawler.insert_one(
                            {'url': second_url, 'last_updated': title + publish_date, 'origin': gov_name})
                if db[collection_name].count_documents({'url': anc_url}) == 0:
                    info = {
                        'title': title,
                        'publishDate': publish_date,
                        'text': anc_url,##url有唯一索引，这里变成text
                        'type': '行政处罚决定',
                        'origin': gov_name,
                        'status': 'not parsed'
                    }
                    logger.info('{} 新公告：{} url: {}'.format(gov_name, info['title'], title + publish_date))
                    if info not in result_list:
                        result_list.append(info)
                else:
                    if config['crawler_update_type']['update_type'] == '0':
                        break
            except Exception as e:
                logger.error(e)
                logger.warning('提取公告url出现问题')
                continue
        if stop_flag == True:
            logger.info('到达上次爬取的链接')
            break
        page_num += 1
        if page_num > page_count:
            break
        data2['page'] = page_num
        response = request_site_page(second_url, params=data2, methods='post')
        response.encoding = response.apparent_encoding
        if response is None:
            logger.error('网页请求错误{}'.format(second_url))
        soup = bs(response.content if response else '', 'lxml')

    if len(result_list) > 0:
        logger.info('{}一共有{}条新公告，导入数据库中......'.format(gov_name, len(result_list)))
        r = db[collection_name].insert_many(result_list)
        if len(r.inserted_ids) == len(result_list):
            logger.info('{}公告导入完成！'.format(gov_name))
        else:
            logger.error('{}公告导入出现问题！'.format(gov_name))
    else:
        logger.info('{}没有新公告！'.format(gov_name))


if __name__ == '__main__':
    crawler()
