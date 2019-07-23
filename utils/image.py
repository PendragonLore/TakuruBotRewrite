import asyncio
import functools
import hashlib
import multiprocessing
import sys
import textwrap
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


class ImageIO(BytesIO):
    def __init__(self, initial_bytes=None):
        super().__init__(initial_bytes)

        self._hash = None

    def __repr__(self):
        # caching purposes
        # TODO: use perceptual hashing
        if self._hash is None:
            self._hash = hashlib.sha256(self.getvalue()).hexdigest()

        return f"<ImageIO hash={self._hash}>"


async def run_in_proc(__time, func, *args, **kwargs):
    queue = multiprocessing.Queue()

    def wrapper():
        try:
            ret = func(*args, **kwargs)
        except BaseException as e:
            queue.put_nowait(e)
        else:
            queue.put_nowait(ret)
        finally:
            # idc for the exit code so let's just do 0
            return sys.exit(0)

    proc = multiprocessing.Process(target=wrapper, daemon=True)
    proc.start()

    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, queue.get), timeout=__time)
    except asyncio.TimeoutError:
        proc.kill()
        raise


def process(timeout=None):
    def outer(func):
        @functools.wraps(func)
        async def inner(*args, **kwargs):
            result = await run_in_proc(timeout, func, *args, **kwargs)

            if isinstance(result, BaseException):
                raise result
            return result

        return inner

    return outer


@process(10)
def draw_text_on_img(text, width, image, font, coordinates, font_size=40, text_color=(0, 0, 0)):
    text = textwrap.wrap(text, width=width)
    ret = BytesIO()

    with Image.open(image) as img:
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font, font_size)

        x = coordinates[0]
        y = coordinates[1]
        for t in text:
            width, height = font.getsize(t)
            draw.text((x, y), t, font=font, fill=text_color)
            y += height

        img.save(ret, "png")

    ret.seek(0)

    return ret


@process(10)
def gayify_func(user_avatar, alpha):
    ret = BytesIO()

    with Image.open(user_avatar) as background:
        background = background.resize((926, 926)).convert("RGBA")

        with Image.open("assets/images/gay.png") as flag:
            flag.putalpha(alpha)

            gay = Image.alpha_composite(background, flag)

            gay.save(ret, "png")

    ret.seek(0)

    return ret


async def get_avatar(user):
    ret = ImageIO()
    await user.avatar_url_as(format="png", size=1024).save(ret)

    return ret
