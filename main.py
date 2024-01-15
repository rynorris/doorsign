from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY  # 7.3"
from machine import Pin, SPI
import jpegdec
import sdcard
import os
import inky_frame
import random


IMG_DIR = "/sd/images"

STATUSES = ["IN_A_MEETING", "WRITING_CODE", "AT_LUNCH", "OUT_OF_OFFICE"]
CAPTIONS = [
    "In a meeting",
    "Writing code",
    "At lunch",
    "Done for the day",
]
BUTTONS = [
    inky_frame.button_a,
    inky_frame.button_b,
    inky_frame.button_c,
    inky_frame.button_d,
    # inky_frame.button_e,
]

WIDTH = 800
HEIGHT = 480

CAPTION_FONT = "bitmap8"
CAPTION_SCALE = 2
CAPTION_MARGIN = 5

CAPTION_HEIGHT = CAPTION_SCALE * 8
CAPTION_BOX_HEIGHT = CAPTION_HEIGHT + CAPTION_MARGIN * 2
CAPTION_BOX_Y = HEIGHT - CAPTION_BOX_HEIGHT
CAPTION_Y = CAPTION_BOX_Y + CAPTION_MARGIN


# set up the display
graphics = PicoGraphics(DISPLAY)
graphics.set_font(CAPTION_FONT)

# set up the SD card
sd_spi = SPI(0, sck=Pin(18, Pin.OUT), mosi=Pin(19, Pin.OUT), miso=Pin(16, Pin.OUT))
sd = sdcard.SDCard(sd_spi, Pin(22))
os.mount(sd, "/sd")

# Create a new JPEG decoder for our PicoGraphics
j = jpegdec.JPEG(graphics)


def display_image(filename, caption=None):

    # Open the JPEG file
    j.open_file(filename)

    # Decode the JPEG
    print("Decoding JPEG...")
    j.decode(0, 0, jpegdec.JPEG_SCALE_FULL)

    if caption:
        graphics.set_pen(0)
        graphics.rectangle(0, CAPTION_BOX_Y, WIDTH, CAPTION_BOX_HEIGHT)
        graphics.set_pen(1)
        graphics.text(caption, 5, CAPTION_Y, WIDTH, CAPTION_SCALE)

    # Display the result
    print("Updating display...")
    graphics.update()


def choose_image(status):
    files = os.listdir(IMG_DIR)
    files = [f for f in files if f.startswith(status) and f.endswith(".small.jpg")]
    file = files[random.randrange(len(files))]
    return f"{IMG_DIR}/{file}"


while True:
    print("Going to sleep...")

    inky_frame.turn_off()

    if inky_frame.woken_by_button():
        try:
            ix, button = next((item for item in enumerate((b for b in BUTTONS)) if item[1].read()))
        except StopIteration:
            continue

        for b in BUTTONS:
            b.led_off()

        button.led_on()

        status = STATUSES[ix]
        print(f"Status: {status}")

        caption = CAPTIONS[ix]
        file = choose_image(status)

        print(f"Selected image: {file}")
        display_image(file, caption=caption)

        print("Done")

