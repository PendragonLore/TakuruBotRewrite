import asyncio
import colorsys
import contextlib
import functools
import hashlib
import multiprocessing
import sys
import textwrap
from io import BytesIO

import numpy
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import convolve2d


@contextlib.contextmanager
def bytesio_seek_0():
    ret = BytesIO()
    yield ret
    ret.seek(0)


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

    with Image.open(image) as img:
        draw = ImageDraw.Draw(img)
        font = ImageFont.truetype(font, font_size)

        x = coordinates[0]
        y = coordinates[1]
        for t in text:
            width, height = font.getsize(t)
            draw.text((x, y), t, font=font, fill=text_color)
            y += height

        with bytesio_seek_0() as ret:
            img.save(ret, "png")

    return ret


@process(10)
def gayify_func(user_avatar, alpha):
    with Image.open(user_avatar) as background:
        background = background.resize((926, 926)).convert("RGBA")

        with Image.open("assets/images/gay.png") as flag:
            flag.putalpha(alpha)

            with Image.alpha_composite(background, flag) as gay:
                with bytesio_seek_0() as ret:
                    gay.save(ret, "png")

    return ret


@process(10)
def idfk(img, reverse=True):
    with Image.open(img) as img:
        arr = numpy.array(img)

    first_dimension = arr.shape[0]

    div = int(first_dimension / 2)

    if reverse:
        arr[::-1][div:first_dimension] = arr[div:first_dimension]
    else:
        arr[::-1][:div] = arr[:div]

    with bytesio_seek_0() as ret:
        Image.fromarray(arr).save(ret, format="png")

    return ret


def do_normalise(imc):
    return -numpy.log(1 / ((1 + imc) / 257) - 1)


def undo_normalise(imc):
    return (1 + 1 / (numpy.exp(-imc) + 1) * 257).astype("uint8")


def rotation_matrix(theta):
    return numpy.c_[
        [1, 0, 0],
        [0, numpy.cos(theta), -numpy.sin(theta)],
        [0, numpy.sin(theta), numpy.cos(theta)]
    ]


@process(10)
def yeet(img):
    frames = []

    with Image.open(img) as notarray:
        a = notarray.convert("RGB").resize(tuple(int(x / 2) for x in notarray.size))
        im = numpy.array(a)

    def update(i):
        im_rotated = numpy.einsum("ijk,lk->ijl", do_normalise(im), rotation_matrix(i * numpy.pi / 10))
        actual = undo_normalise(im_rotated)

        frames.append(Image.fromarray(actual))

    for k in range(20):
        update(k)

    with bytesio_seek_0() as ret:
        frames[0].save(ret, format="GIF", append_images=frames[1:], save_all=True, duration=100, loop=0)

    return ret


@process(20)
def speblur(img, w, mode):
    window = numpy.ones((w, w))
    window /= numpy.sum(window)

    with Image.open(img) as image:
        array = numpy.array(image.resize(tuple(int(x / 2) for x in image.size)).convert("RGB"))

    imgs = []

    for k in range(3):
        if k == mode:
            im_conv_d = convolve2d(array[:, :, k], window, mode="same", boundary="symm")
        else:
            im_conv_d = array[:, :, k]
        imgs.append(im_conv_d)

    with bytesio_seek_0() as ret:
        Image.fromarray(numpy.stack(imgs, axis=2).astype("uint8")).save(ret, format="png")

    return ret


@process(10)
def shitsort(img):
    with Image.open(img) as image:
        array = numpy.array(image.convert("RGB"))

    array.sort(axis=1)

    with bytesio_seek_0() as ret:
        Image.fromarray(array).save(ret, format="png")

    return ret


@process(10)
def gcsort(img):
    with Image.open(img) as img:
        array = numpy.array(img.resize(tuple(int(x / 2) for x in img.size)).convert("RGB"))

    imgs = []

    new = array.copy()
    for index, sub in enumerate(array):
        record = -1
        selected = index
        for j, subar in enumerate(sub):
            b = colorsys.rgb_to_hsv(subar[0], subar[1], subar[2])[0]
            if b > record:
                selected = j
                record = b
        tmp = array[index]
        new[index] = array[selected]
        new[selected] = tmp
        imgs.append(Image.fromarray(new.copy()))

    with bytesio_seek_0() as ret:
        imgs[0].save(ret, format="gif", duration=1, loop=0, save_all=True, append_images=imgs[1:])

    return ret


async def get_avatar(user):
    ret = ImageIO()
    await user.avatar_url_as(format="png", size=1024).save(ret)

    return ret
