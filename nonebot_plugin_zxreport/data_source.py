import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
from httpx import Response, HTTPStatusError, TimeoutException, ConnectError
from nonebot.utils import run_sync
from nonebot.log import logger
from nonebot_plugin_htmlrender import template_to_pic
import tenacity
from zhdate import ZhDate
from tenacity import retry, stop_after_attempt, wait_fixed


from .config import (
    REPORT_PATH,
    TEMPLATE_PATH,
    Anime,
    Hitokoto,
    SixData,
    favs_arr,
    favs_list,
)


class AsyncHttpx:
    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=(
            tenacity.retry_if_exception_type(
                (TimeoutException, ConnectError, HTTPStatusError)
            )
        ),
    )
    async def get(cls, url: str) -> Response:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response
            except (TimeoutException, ConnectError, HTTPStatusError) as e:
                logger.error(f"Request to {url} failed due to: {e}")
                raise


@run_sync
def save(data: bytes):
    file_path = REPORT_PATH / f"{datetime.now().date()}.png"
    with open(file_path, "wb") as file:
        file.write(data)


class Report:
    hitokoto_url = "https://v1.hitokoto.cn/?c=a"
    six_url = "https://60s.viki.moe/?v2=1"
    game_url = "https://www.4gamers.com.tw/rss/latest-news"
    bili_url = "https://s.search.bilibili.com/main/hotword"
    it_url = "https://www.ithome.com/rss/"
    anime_url = "https://api.bgm.tv/calendar"

    week = {  # noqa: RUF012
        0: "一",
        1: "二",
        2: "三",
        3: "四",
        4: "五",
        5: "六",
        6: "日",
    }

    @classmethod
    async def get_report_image(cls) -> bytes:
        """获取数据"""
        now = datetime.now()
        file = REPORT_PATH / f"{now.date()}.png"
        if file.exists():
            with file.open("rb") as image_file:
                return image_file.read()
        zhdata = ZhDate.from_datetime(now)
        data = {
            "data_festival": cls.festival_calculation(),
            "data_hitokoto": await cls.get_hitokoto(),
            "data_bili": await cls.get_bili(),
            "data_six": await cls.get_six(),
            "data_anime": await cls.get_anime(),
            "data_it": await cls.get_it(),
            "week": cls.week[now.weekday()],
            "date": now.date(),
            "zh_date": zhdata.chinese().split()[0][5:],
        }
        image_bytes = await template_to_pic(
            template_path=str((TEMPLATE_PATH / "mahiro_report").absolute()),
            template_name="main.html",
            templates={"data": data},
            pages={
                "viewport": {"width": 578, "height": 1885},
                "base_url": f"file://{TEMPLATE_PATH}",
            },
            wait=2,
        )
        await save(image_bytes)
        return image_bytes

    @classmethod
    def festival_calculation(cls) -> list[tuple[str, str]]:
        """计算节日"""
        base_date = datetime(2016, 1, 1)
        n = (datetime.now() - base_date).days
        result = []

        for i in range(0, len(favs_arr), 2):
            if favs_arr[i] >= n:
                result.extend(
                    (favs_arr[i + j] - n, favs_list[favs_arr[i + j + 1]])
                    for j in range(0, 14, 2)
                )
                break
        return result

    @classmethod
    async def get_hitokoto(cls) -> str:
        """获取一言"""
        res = await AsyncHttpx.get(cls.hitokoto_url)
        data = Hitokoto(**res.json())
        return data.hitokoto

    @classmethod
    async def get_bili(cls) -> list[str]:
        """获取哔哩哔哩热搜"""
        res = await AsyncHttpx.get(cls.bili_url)
        data = res.json()
        return [item["keyword"] for item in data["list"]]

    @classmethod
    async def get_six(cls) -> list[str]:
        """获取60s看时间数据"""
        res = await AsyncHttpx.get(cls.six_url)
        data = SixData(**res.json())
        return data.data.news[:11] if len(data.data.news) > 11 else data.data.news

    @classmethod
    async def get_it(cls) -> list[str]:
        """获取it数据"""
        res = await AsyncHttpx.get(cls.it_url)
        root = ET.fromstring(res.text)
        titles = []
        for item in root.findall("./channel/item"):
            title_element = item.find("title")
            if title_element is not None:
                titles.append(title_element.text)
        return titles[:11] if len(titles) > 11 else titles

    @classmethod
    async def get_anime(cls) -> list[tuple[str, str]]:
        """获取动漫数据"""
        res = await AsyncHttpx.get(cls.anime_url)
        data_list = []
        week = datetime.now().weekday()
        try:
            anime = Anime(**res.json()[week])
        except IndexError:
            anime = Anime(**res.json()[-1])
        data_list.extend(
            (data.name_cn or data.name, data.image) for data in anime.items
        )
        return data_list[:8] if len(data_list) > 8 else data_list
