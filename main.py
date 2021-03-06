import requests
from bs4 import BeautifulSoup
import csv
import sys
import os
import re
from multiprocessing import Lock
import queue
import threading

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "es",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"
}

# field names of our csv file.
variables = ['uid', #unique code to differentiate each row
             'price_euro',  # Mandatory
             'district',  # Mandatory
             'area',  # Mandatory
             'room_num',  # Mandatory
             'bath_num',  # Mandatory
             'furnished',  # Important info that affect the price
             'has_parking',  # Important info that affect the price
             'has_elevator',  # Important info that affect the price
             'has_air',  # Important info that affect the price
             # Contain detail information the distribution of the rooms, kitchen, etc.
             'distributions_detail',
             'features_detail',  # detail info contains featureas of the floor which affect the price
             'name',  # contains useful information
             'description'  # contains a description written by the owner which contains useful information
             ]

# you can search rent or sale informaticon
rent = 'alquiler'
sale = 'viviendas'


bf4parser = 'lxml'


def valid_url(url):
    """some url are invalid because the data are not belong to the original web, they belong to the partner web site."""
    if re.match(r"^https:.*?.com/f[a|v]\d+$", url):
        return False
    return True


def request_page_number(search_type, city_name):
    """given the search_type and city_name return the number of pagination"""
    try:
        url = 'https://www.habitaclia.com/{}-{}.htm'.format(
            search_type, city_name)
        page = requests.get(url, headers=headers)
        soup = BeautifulSoup(page.text, features=bf4parser)
        aside = soup.find(id='js-nav')
        li_next = aside.find('li', {'class': 'next'})
        if li_next == None:
            return 1
        else:
            max_page_text = li_next.previous_element.find_previous_sibling(
                'li').text.strip('\n')
            if max_page_text.isdigit():
                return int(max_page_text)
            else:
                raise Exception(
                    'incorrect page number:[{}]'.format(max_page_text))
    except Exception as e:
        print('Unknow error while getting max page number:', str(e))
        sys.exit(0)


def build_page_url(search_type, city_name, page_idx):
    url = 'https://www.habitaclia.com/{}-{}{}.htm'.format(search_type, city_name,
                                                          '' if page_idx == 0 else '-'+str(page_idx))
    return url


def requests_pages(search_type, city_name, page_idx=None):
    """request url of each pagination"""
    try:
        # first page without index, the rest we need concat the page index
        page = requests.get(build_page_url(search_type,
                                           city_name, page_idx), headers=headers)
        soup = BeautifulSoup(page.text, features=bf4parser)
        section = soup.find('section', {'class': 'list-items'})
        all_articles = section.find_all('article')

        result = []
        # only articles with data-href
        for article in all_articles:
            if 'data-href' in article.attrs and valid_url(article['data-href']):
                result.append(article['data-href'])

        return result
    except Exception as e:
        print('Unknow error while requesting pages:', str(e))


def true_false_none(true_str, false_str, *search_texts):
    """search in the text if contain some string and return TRUE,FALSE or None"""
    result = None
    for text in search_texts:
        if true_str in text.lower():
            result = True
        if false_str in text.lower():
            result = False
    return result


def get_features(detail_container):
    """get list of feature of each floor"""
    features = []
    general_feature_detail = detail_container.find(
        'h3', string='Características generales')

    if general_feature_detail != None:
        ul_node = general_feature_detail.find_next('ul')

        feature_list = ul_node.find_all('li', attrs={'class': None})

        for each in feature_list:
            text = each.string.strip()
            features.append(text)

    community_equipment = detail_container.find(
        'h3', string='Equipamiento comunitario')

    if community_equipment != None:
        ul_node = community_equipment.find_next('ul')
        equipment_list = ul_node.find_all('li')
        for each in equipment_list:
            text = each.string.strip()
            features.append(text)

    return features


def get_distribution(detail_container):
    """get list of distribution of each floor"""
    distribution = []
    distribution_detail = detail_container.find(
        'h3', string='Distribución')
    if distribution_detail != None:
        ul_node = distribution_detail.find_next('ul')
        distribution_list = ul_node.find_all('li')

        for each in distribution_list:
            text = each.text.strip()
            distribution.append(text)

    return distribution


def resquest_each_page(url):
    page = requests.get(url, headers=headers)
    return page.text

def clean_price(price):
   return price.replace('€','').replace('.','').replace(' ','')

def resolve_each_page(text):
    """the main function of this scraper resolve the page and return the result"""
    result = None
    soup = BeautifulSoup(text, features=bf4parser)
    summary = soup.find('div', {'class': 'summary-left'})
    price = summary.find('div', {'class': 'price'}).find(
        'span', {'class': 'font-2'}).string
    
    if('consultar' in price.lower()):
        return None
    
    price = clean_price(price)
    
    name = summary.h1.text.replace('\n', '.').replace('\r', '.')

    if summary.find(id='js-ver-mapa-zona') == None:
        return None

    district = summary.find(id='js-ver-mapa-zona').string.strip()

    feature_container = summary.find(
        'ul', {'class': 'feature-container'}).find_all('li')

    area = None
    roomNum = None
    bathNum = None

    for feature in feature_container:
        if 'm2' in feature.text and '€/m2' not in feature.text:
            area = re.findall('[0-9]+', feature.text)[0]
        if 'hab.' in feature.text:
            roomNum = re.findall('[0-9]+', feature.text)[0]
        if 'baño' in feature.text:
            bathNum = re.findall('[0-9]+', feature.text)[0]

    detail_container = soup.find('section', {'class': 'detail'})

    description = '{}.{}'.format(detail_container.find(id='js-detail-description-title').text,
                                 detail_container.find(id='js-detail-description').text)
    description = description.replace('\r', '.').replace('\n', '.')
    features = get_features(detail_container)
    distributions = get_distribution(detail_container)

    # The following variables can be TRUE,FALSE or None
    furnished = None
    has_parking = None
    has_air = None
    has_elevator = None

    for text in features:
        text_lower = text.lower()
        if 'plaza parking' in text_lower:
            has_parking = true_false_none(
                'plaza parking', 'sin plaza parking', text)
        if 'amueblado' in text_lower or 'sin amueblar' in text_lower:
            furnished = true_false_none('amueblado', 'sin amueblar', text)
        if 'aire acondicionado' in text_lower:
            has_air = true_false_none(
                'aire acondicionado', 'sin aire acondicionado', text)
        if 'ascensor' in text_lower:
            has_elevator = true_false_none('ascensor', 'sin ascensor', text)

    features_detail = "%;%".join(features)
    distributions_detail = "%;%".join(distributions)
    result = {
        'price_euro': price,
        'district': district,
        'area': area,
        'room_num': roomNum,
        'bath_num': bathNum,
        'furnished': furnished,
        'has_parking': has_parking,
        'has_elevator': has_elevator,
        'has_air': has_air,
        'distributions_detail': distributions_detail,
        'features_detail': features_detail,
        'name': name,
        'description': description
    }
    return result


def get_pages_url_worker(max_page_number, resolve_threads_number, search_type, city_name, pages_url_queue):
    """worker that get url from each page"""
    count = 0
    for page_idx in range(max_page_number):
        pages = requests_pages(search_type, city_name, page_idx)
        for page in pages:
            count = count + 1
            pages_url_queue.put([count, page])
    for _ in range(resolve_threads_number):
        pages_url_queue.put('stop')


def page_resolve_worker(pages_url_queue,  result_queue, print_lock):
    """worker that resolve each page_url in the pages_url_queue and store result in result_queue"""
    while True:
        data = pages_url_queue.get()
        if data == 'stop':
            break

        cout, page_url = data
        with print_lock:
            print('Resolving Page:{},Count:{}, URL:{},'.format(
                cout//16+1, cout, page_url))
        try:
            html_text = resquest_each_page(page_url)
            result = resolve_each_page(html_text)

            if result == None:
                with print_lock:
                    print('ERROR!!!!NOT ENOUGH DATA!!!:{},\n'.format(page_url))
            else:
                result_queue.put(result)
        except Exception as e:
            with print_lock:
                print('UNEXPECTED EROOR:[{}]!!:{}\n'.format(str(e), page_url))
        finally:
            pages_url_queue.task_done()
    result_queue.put('stop')


def write_file_worker(writer, file_lock, result_queue, resolve_threads_number):
    """worker that store date in csv file"""
    done_count = 0
    uid = 0
    while True:
        try:
            result = result_queue.get()
            uid = uid+1
            result['uid'] = uid
            if result == 'stop':
                done_count = done_count+1
                if resolve_threads_number == done_count:
                    break
                else:
                    continue
        except Exception:
            print("No more element to write in file")
            break
        with file_lock:
            writer.writerow(result)
        result_queue.task_done()


def main(city_name, search_type):

    # Get max page to resolve
    max_page_number = request_page_number(search_type, city_name)
    print('Max page number is:[{}], estimate url to resolve:[{}]'.format(
        max_page_number, max_page_number*15))

    # lock to avoid race condition
    file_lock = Lock()
    print_lock = Lock()
    # Queue for store the page result to store in the csv file
    result_queue = queue.Queue()
    # Queue for store pages that need be resolved
    pages_url_queue = queue.Queue(max(os.cpu_count()*20, 10))

    csvfile = open('dataset.csv', 'w', newline='', encoding='utf-8')
    writer = csv.DictWriter(csvfile, fieldnames=variables)
    writer.writeheader()

    resolve_threads_number = min(15, os.cpu_count()*4)
    resolve_threads_list = []
    # Thread that get pages
    get_pages_thread = threading.Thread(target=get_pages_url_worker, args=(
        max_page_number, resolve_threads_number, search_type, city_name, pages_url_queue), name='Thread get page worker')
    get_pages_thread.start()

    # Threads that store data in csv file
    write_file_thread = threading.Thread(
        target=write_file_worker, args=(writer, file_lock, result_queue, resolve_threads_number))
    write_file_thread.start()

    threads = []
    # Threads that resolve all pages
    for x in range(resolve_threads_number):
        t = threading.Thread(target=page_resolve_worker, args=(
            pages_url_queue,  result_queue, print_lock, ), name='Thread resolver '+str(x))
        threads.append(t)
        t.start()
        resolve_threads_list.append(t)

    # block until all tasks are done
    pages_url_queue.join()
    result_queue.join()
    get_pages_thread.join()
    for t in threads:
        t.join()
    write_file_thread.join()


def test_page(page_url):
    html_text = resquest_each_page(page_url)
    result = resolve_each_page(html_text)
    print(result)


if __name__ == "__main__":
    # you can search rent or sale informaticon by setting rent or sale
    city_name = 'barcelona'
    search_type = rent
    main(city_name, search_type)