from pathlib import Path

import scrapy
from scrapy import Selector


class ProxyRefresherSpider(scrapy.Spider):
    name = "proxy_refresher"
    start_urls = [
        "https://free-proxy-list.net/en/",
    ]

    async def start(self):
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response, **kwargs):
        html_to_parse = response.body.decode("utf-8")
        selector = Selector(text=html_to_parse)
        # alcoteka на https, поэтому выбираем только https = 'yes' прокси
        servers_list = selector.xpath(
            "//div[2]/div/table/tbody/tr/td[7][contains(text(), 'yes')]//preceding-sibling::td[6]//text()"
        ).getall()
        ports_list = selector.xpath(
            "//div[2]/div/table/tbody/tr/td[7][contains(text(), 'yes')]//preceding-sibling::td[5]//text()"
        ).getall()
        proxies = ""
        counter = 0
        for item in zip(servers_list, ports_list):
            current_proxy = f"https://{item[0]}:{item[1]}\n"
            proxies += current_proxy
            counter += 1
            self.log(f"Added proxy {current_proxy}")
            if counter >= 5:
                self.log(f"added only {counter} most recently checked proxies")
                break
        proxies = proxies[:-1]
        filename = "../proxy_list.txt"
        Path(filename).write_text(proxies, encoding="utf-8")
        self.log(f"Proxies at {filename}")
