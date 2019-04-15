from bs4 import BeautifulSoup
from urllib.parse import urlencode
import requests
from requests.exceptions import RequestException
import json
import re
from config import *
import pymongo
import os
from hashlib import md5
from multiprocessing import Pool

client = pymongo.MongoClient(MONGO_URL, connect=False)
db = client[MONGO_DB]


# 加载单个Ajax请求
def get_page_index(offset, keyword):
    data = {
        'aid': '24',
        'app_name': 'web_search',
        'ofset': offset,
        'format': 'json',
        'keyword': keyword,
        'autoload': 'true',
        'count': '20',
        'en_qc': '1',
        'cur_tab': '1',
        'from': 'search_tab',
        'pd': 'synthesis',
        'timestamp': '1553708373325'
    }
    url = 'https://www.toutiao.com/api/search/content/?aid=24&app_name=web_search?' + urlencode(data) #构建url
    # 定义headers，模拟浏览器访问
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36'}
    # 加一个判断来判断是否请求成功
    try:
        response = requests.get(url, headers=headers) #发送请求
        if response.status_code == 200: #判断响应码是不是200，是200则表示请求成功
            return response.text
        return None
    except RequestException:
        print('请求出错', url)
        return None

# 提取每一个图集的url
def parse_page_index(html):
    data = json.loads(html)
    if data and 'data' in data.keys():
        for item in data.get('data'):
            yield item.get('article_url')

# 请求单个图集
def get_page_detail(url):
    headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return url
    except RequestException:
        return None

# 获得每一个图集网页代码，并从中提取标题，图片的url
def parse_page_detail(html, url):
    soup = BeautifulSoup(html, 'lxml') #初始化
    result = soup.select('title') #用BeautifulSoup选择标题
    title = result[0].get_text() if result else '' #防止出现没有标题的情况导致程序报错
    images_pattern = re.compile('gallery: JSON.parse\("(.*)"\)', re.S) #将正则字符串编译成正则表达式对象
    result = re.search(images_pattern, html) #送search()匹配图片的url
    # 构造一个生成器将图片的url，图片所属的标题，以及图集的url一并返回
    if result:
        data = json.loads(result.group(1).replace('\\', ''))
        if data and 'sub_images' in data.keys():
            sub_images = data.get('sub_images')
            images = [item.get('url') for item in sub_images]
            for image in images:download_image(image) #下载图片
            return {
                        'title': title,
                        'url': url,
                        'images': images
                        }

# 写入MongoDB
def save_to_mongo(result):
    if (result != None) and (db[MONGO_TABLE].insert_one(result)):
        print('存储成功', result)
        return True
    return False

# 请求图片的url，并且下载图片
def download_image(url):
    print('正在下载', url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.86 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            save_image(response.content) #下载图片
        return None
    except RequestException:
        print('请求图片出错', url)
        return None

#下载图片，将图片保存在本地文档
def save_image(content):
    file_path = '{0}/{1}.{2}'.format(os.getcwd(), md5(content).hexdigest(), 'jpg') #以二进制的形式写入文件，并且用图片的MD5值来命名图片，以免重复
    if not os.path.exists(file_path):
        with open(file_path, 'wb') as f:
            f.write(content)
            f.close()

#构建主函数
def main(offset):
    html = get_page_index(offset, keyword)
    for url in parse_page_index(html):
        html = get_page_detail(url)
        if html:
            result = parse_page_detail(html, url)
            if result:
                save_to_mongo(result)

GROUP_START = 1 #定义起始页
GROUP_END = 20 #定义结束页

if __name__ == '__main__':
    groups = [x*20 for x in range(GROUP_START, GROUP_END + 1)]
    pool = Pool()  #利用多进程初始化
    pool.map(main, groups) # 调用多进程的map()实现多进程下载
