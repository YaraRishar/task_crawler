import json
from datetime import datetime

import scrapy


def parse_product_response(item_data, prepared_dict):
    results = item_data["results"]

    volume = None
    for label in results.get("filter_labels", []):
        if label.get("filter") == "obem" and label.get("values"):
            volume = label["values"]["min"]
            break

    marketing_tags = []
    for label in results.get("filter_labels", []):
        if label.get("title") and label.get("filter") != "obem":
            marketing_tags.append(label["title"])

    brand = "null"
    for block in results.get("description_blocks", []):
        if block.get("code") == "brend" and block.get("values"):
            brand = block["values"][0]["name"]
            break

    section = []
    if results.get("category") and results["category"].get("parent"):
        section.append(results["category"]["parent"]["name"])
    if results.get("category"):
        section.append(results["category"]["name"])

    metadata = {
        "vendor_code": results["vendor_code"],
        "availability_title": results["availability_title"],
    }

    for block in results.get("description_blocks", []):
        if block.get("type") == "select":
            value = ", ".join([str(v["name"]) for v in block["values"]])
            metadata[block["title"]] = value
        elif block.get("type") == "flag":
            metadata[block["title"]] = block.get("placeholder", "")
            continue
        elif block.get("type") == "range":
            if block.get("min") == block.get("max"):
                unit = block.get("unit", "")
                metadata[block["title"]] = f"{block["max"]}{unit}"
                continue
            unit = block.get("unit", "")
            metadata[block["title"]] = f"{block["min"]}-{block["max"]}{unit}"

    for block in results.get("text_blocks", []):
        if block["title"] == "Описание":
            prepared_dict["metadata"]["__description"] = block["content"]
            continue
        metadata[block["title"]] = block["content"]

    prepared_dict["title"] = f"{results["name"]}, {volume} л"
    prepared_dict["brand"] = brand
    prepared_dict["section"] = section
    prepared_dict["metadata"] = metadata

    return prepared_dict


class TestTaskSpider(scrapy.Spider):
    name = "test_task"
    api_url = "https://alkoteka.com/web-api/v1/product/"
    custom_settings = {
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.3",
        "DOWNLOADER_MIDDLEWARES": {
            "test_task.middlewares.ProxyDownloaderMiddleware": 100
        },
        "PATH_TO_PROXIES": "../proxy_list.txt",
    }

    def __init__(self, *args, **kwargs):
        super(TestTaskSpider, self).__init__(*args, **kwargs)
        self.city_uuid = kwargs.get("city_uuid")
        self.use_proxy = kwargs.get("use_proxy")
        self.categories = kwargs.get("categories").split(", ")
        self.categories = [
            "https://alkoteka.com/catalog/vino",
            "https://alkoteka.com/catalog/slaboalkogolnye-napitki-2",
            "https://alkoteka.com/catalog/krepkiy-alkogol",
        ]
        for i in range(len(self.categories)):
            self.categories[i] = self.categories[i].split("/")[-1]

        if self.use_proxy.lower().strip() == "true":
            self.use_proxy = True
        if self.city_uuid is None:
            self.city_uuid = "4a70f9e0-46ae-11e7-83ff-00155d026416"

    async def start(self):
        for category in self.categories:
            parameters = {
                "city_uuid": self.city_uuid,
                "options[tovary-so-skidkoi]": "false",
                "page": "1",
                "per_page": "20",
                "root_category_slug": category,
            }
            yield scrapy.FormRequest(
                url=self.api_url,
                method="GET",
                formdata=parameters,
                headers={"X-Requested-With": "XMLHttpRequest"},
                callback=self.parse_first_page,
                meta={"category": category, "parameters": parameters},
            )

    def parse_first_page(self, response):
        data = json.loads(response.text)
        total_pages = data.get("meta", {}).get("total", 1)

        # ограничение на количество заявок для парсинга: по условиям тестового
        # задания, товаров должно быть от 100 шт. на категорию
        total_wares = total_pages * 20
        if total_wares > 100:
            total_pages = 7

        category = response.meta["category"]
        base_parameters = response.meta["parameters"]

        for page in range(1, total_pages + 1):
            parameters = base_parameters.copy()
            parameters["page"] = str(page)

            yield scrapy.FormRequest(
                url=self.api_url,
                method="GET",
                formdata=parameters,
                headers={"X-Requested-With": "XMLHttpRequest"},
                callback=self.parse,
                meta={"category": category},
            )

    def parse(self, response, **kwargs):
        data = json.loads(response.text)

        for item in data["results"]:
            price = item["price"]
            prev_price = item["prev_price"]
            sale_tag = 0
            if prev_price is not None:
                sale_tag = str(round(100 * (prev_price - price) / prev_price))

            marketing_tags = [i["title"] for i in item["action_labels"]]
            results = {
                "timestamp": int(datetime.now().timestamp()),
                "RPC": item["uuid"],
                "url": item["product_url"],
                "title": "",
                "marketing_tags": marketing_tags,
                "brand": "",
                "section": [""],
                "price_data": {
                    "current": float(price),
                    "original": float(prev_price) if prev_price is not None else price,
                    "sale_tag": f"Скидка {sale_tag}%",
                },
                "stock": {
                    "in_stock": item["available"],
                    "count": item["quantity_total"],
                },
                "assets": {
                    "main_image": item["image_url"],
                    "set_images": [item["image_url"]],
                    "view360": ["null"],
                    "video": ["null"],
                },
                "metadata": {},
                "variants": 1,
            }

            item_name = item["product_url"].split("/")[-1]
            parameters = {"city_uuid": self.city_uuid}

            yield scrapy.FormRequest(
                url=self.api_url + item_name,
                method="GET",
                formdata=parameters,
                headers={"X-Requested-With": "XMLHttpRequest"},
                callback=self.parse_item_page,
                meta={"results": results},
            )

    @staticmethod
    def parse_item_page(response):
        item_data = json.loads(response.text)
        parsed_product = parse_product_response(
            item_data, prepared_dict=response.meta["results"]
        )
        yield parsed_product
