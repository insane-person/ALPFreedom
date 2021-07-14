import requests
import json
from typing import Optional
import os
import jmespath

def actual_kwargs():
    """
    Decorator that provides the wrapped function with an attribute 'actual_kwargs'
    containing just those keyword arguments actually passed in to the function.
    """
    def decorator(function):
        def inner(*args, **kwargs):
            inner.actual_kwargs = kwargs
            return function(*args, **kwargs)
        return inner
    return decorator


class Connection:
    route_complexities = {
        1:  '1Б',
        21: '1Б*',
        2:  '2А',
        3:  '2А*',
        4:  '2Б',
        5:  '2Б*',
        6:  '3А',
        7:  '3А*',
        8:  '3Б',
        9:  '3Б*',
        10: '4А',
        11: '4А*',
        12: '4Б',
        13: '4Б*',
        14: '5А',
        15: '5А*',
        16: '5Б',
        17: '5Б*',
        18: '6А',
        19: '6А*',
        20: '6Б'
    }

    route_types = {
        'к': 1,
        'л': 2,
        'лс': 3,
        'ск': 4,
        'сн': 5,
    }

    def __init__(self, host: str, debug: Optional[bool] = False) -> None:
        self.host = host
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0'
        self.session = requests.Session()
        self.chunk_size = 2048

        if debug:
            import logging
            import http.client as http_client
            http_client.HTTPConnection.debuglevel = 1
            logging.basicConfig()
            logging.getLogger().setLevel(logging.DEBUG)
            requests_log = logging.getLogger("requests.packages.urllib3")
            requests_log.setLevel(logging.DEBUG)
            requests_log.propagate = True

        responce = self.session.get(self.host,
                                    headers={'User-Agent': self.user_agent})

        self.mountain_ranges = []
        self.mountain_regions = []
        self.loaded_mountain_ranges_id = []

    def get_mountain_ranges(self) -> list:
        """
        Запрашивает существующие в каталоге районы
        :return:
        """
        responce = requests.get('https://alpfederation.ru/api/mountainregions')
        self.mountain_ranges = json.loads(responce.text)
        return [x for x in self.mountain_ranges]

    def get_mountain_regions(self, mountain_range_id: int) -> None:
        """
        Запрашивает отдельные хребты района
        :param mountain_range_id: Район
        :return:
        """
        if not mountain_range_id in self.loaded_mountain_ranges_id:
            self.loaded_mountain_ranges_id.append(mountain_range_id)
            responce = requests.get('https://alpfederation.ru/api/mountainareas/' + str(mountain_range_id))
            current_regions = json.loads(responce.text)
            self.mountain_regions.extend(current_regions)
            return current_regions
        else:
            result = [x for x in self.mountain_regions
                      if x['mountain_region_id'] == mountain_range_id]
            return result

    def get_all_regions(self):
        for range in self.mountain_ranges:
            self.get_mountain_regions(range['id'])

    def get_region_summits(self, mountain_region_id: int) -> None:
        """

        :param mountain_region_id:
        :return:
        """
        responce = requests.get(f'https://alpfederation.ru/api/mountains/{mountain_region_id}/by/area')
        mountains = json.loads(responce.text)
        # TODO Неверно считает высоту т.к. встречаются сборки вершин. Нужно парсить отдельно
        return jmespath.search('[].mountain_peaks[0].{name: short_mountain_name, height: height, id: mountain_id}', mountains)

    @actual_kwargs()
    def get_routes(self,
                   region_id=None,
                   area_id=None,
                   mountain_id=None,
                   route_complexities=None,
                   route_types=None,
                   peak_height_min=None,
                   peak_height_max=None,
                   ):
        # TODO fix hardcode value
        data = {
        #     'area_id': 0,
        #     'region_id': 0,
        #     'mountain_id': 0,
        #     # 'route_complexities[]': 0,  # Optional 0 - all routes else mountain id
        #     # 'route_types[]': 0,
            'peak_height_min': 0,
            'peak_height_max': 8848,
            'order_by': '',
            'offset': 0,
            'limit': 100  # TODO check limit and use offset in the future
        }
        parameters = self.get_routes.actual_kwargs
        parameters.update(data)

        responce = requests.get('https://alpfederation.ru/api/mountainroutes', parameters,
                                headers={'User-Agent': self.user_agent})
        mountainroutes = json.loads(responce.text)
        return mountainroutes

    def get_description_file(self, file_id: int, path: Optional[str] = None, filename: Optional[str] = None) -> None:
        responce = requests.get('https://alpfederation.ru/api/files/' + str(file_id), stream=True)

        if not filename:
            # TODO fix parsing of content disposition
            header_name = responce.headers['Content-Disposition']
            import re
            result = re.search('(?:attachment; filename=")(.+)(?:")', header_name)
            filename = result[1]

        filename = os.path.basename(filename)

        if path:
            path = os.path.abspath(path)
            file_path = os.path.join(path, filename)
        else:
            file_path = filename

        with open(file_path, 'wb') as fd:
            for chunk in responce.iter_content(self.chunk_size):
                fd.write(chunk)