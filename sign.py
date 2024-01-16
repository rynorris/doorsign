import base64
from dataclasses import dataclass, asdict
import json
import os
import requests
import sqlite3
import sys
import time
import uuid
from PIL import Image


DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480


GPT_4_TURBO = "gpt-4-1106-preview"

SYSTEM_PROMPT = """
You are a key part of a system which generates images to display on the sign on the door of a software engineer's office.

The office can be in several states such as DEEP_FOCUS, CHILLING or IN_A_MEETING.

Your role is to generate a text prompt to be sent to an AI image-generation model, in order to generate an image which effectively communicates the current office status.
You should ensure that the images are creative and interesting. For example by using animals, robots, or anthropomorphised objects rather than humans.

You MUST reply in the following format:
{output_format}

For example:
{examples}
"""


@dataclass
class DallEPrompt:
    prompt: str
    caption: str

    @classmethod
    def parse(cls, json_string: str) -> "DallEPrompt":
        return cls(**json.loads(json_string))

    def dump(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def description():
        return (
           "a JSON object containing two fields:\n"
           "  - \"prompt\": a brief description of the scene, along with hints as to desired style, medium, lighting, etc."
           "  - \"caption\": a short caption to display on the sign, just in case it's not clear from the image what the status is."
        )

    @staticmethod
    def examples():
        return [
            ("IN_A_MEETING", DallEPrompt(
                prompt="Robots of all shapes and sizes, sitting around a table in a board room. Watercolor.",
                caption="In a meeting"
            )),
            ("CHILLING", DallEPrompt(
                prompt="Kangaroo sunbathing on a beautiful beach. Photorealistic.",
                caption="Just chilling"
            )),
            ("DEEP_FOCUS", DallEPrompt(
                prompt="Anthropomorphic spoon in deep focus, writing code on a laptop made of toast. Detailed pixar-style 3D animation.",
                caption="Deep in focused work"
            )),
        ]


@dataclass
class StableDiffusionPrompt:
    prompt: str
    negativePrompt: str
    caption: str

    @classmethod
    def parse(cls, json_string: str) -> "StableDiffusionPrompt":
        return cls(**json.loads(json_string))

    def dump(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def description():
        return (
            "a JSON object containing two fields:\n"
            "  - \"prompt\": the positive prompt for the image generation, including a brief description "
            "of the scene and a comma-separated list of keywords related to style, medium, lighting, etc.\n"
            "  - \"negativePrompt\": the negative prompt for the image generation, indicating what should be avoided"
        )

    @staticmethod
    def examples():
        return [
            ("IN_A_MEETING", StableDiffusionPrompt(
                prompt="A variety of robots of different shapes and sizes, engaged in a discussion around a sleek, futuristic table in a high-tech boardroom, neon lighting, cyberpunk aesthetic, digital art, 4K resolution",
                negativePrompt="blurry, dark, low resolution, human figures",
                caption="In a meeting",
            )),
            ("CHILLING", StableDiffusionPrompt(
                prompt="A kangaroo lying back on a lounge chair, sunglasses on, with a tropical drink, relaxed on a sunny beach, clear skies, vibrant colors, photorealistic style, high resolution",
                negativePrompt="nighttime, rain, snow, busy, crowded",
                caption="Just chilling",
            )),
            ("DEEP_FOCUS", StableDiffusionPrompt(
                prompt="An anthropomorphic spoon wearing glasses, deeply focused on coding on a laptop made of toast, surrounded by tech gadgets, vibrant yet focused lighting, Pixar-style animation, high detail",
                negativePrompt="blurry, abstract, dark, cluttered",
                caption="Deep in focused work",
            ))
        ]


# AI Functions


def load_api_key():
    with open("/Users/rnorris/security/openai-secret-key") as f:
        return f.read().strip()


def openai_request(api_key, path, body):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    resp = requests.post(f"https://api.openai.com{path}", json=body, headers=headers)

    try:
        resp.raise_for_status()
    except:
        print(resp.text)
        raise
    return resp.json()


def chat_completion(api_key, model, messages):
    data = openai_request(api_key, "/v1/chat/completions", body={"model": model, "messages": messages, "response_format": {"type": "json_object"}})
    return data["choices"][0]["message"]["content"]


def generate_system_prompt(prompt_class):
    description = prompt_class.description()
    examples = "\n".join(["{0} -> {1}".format(inp, out.dump()) for [inp, out] in prompt_class.examples()])
    return SYSTEM_PROMPT.format(output_format=description, examples=examples)


def generate_image(api_key, prompt: DallEPrompt):
    body = {
        "model": "dall-e-3",
        "prompt": prompt.prompt,
        "size": "1792x1024",
        "n": 1,
        "response_format": "b64_json",
    }
    data = openai_request(api_key, "/v1/images/generations", body)
    img = data["data"][0]
    return (img["revised_prompt"], base64.b64decode(img["b64_json"]))


def get_sign_prompt(api_key, system_prompt, status, recent_prompts=None):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": "Here are some of the prompts you recently generated. Make sure the next one is different and creative.\n" + "\n".join(recent_prompts or [])},
        {"role": "user", "content": f"Office status: {status}"},
    ]
    return chat_completion(api_key, GPT_4_TURBO, messages)


# DB Functions


def init_db(cur):
    cur.execute("CREATE TABLE IF NOT EXISTS images(uuid, timestamp, status, prompt, revised_prompt, filename)")


def get_most_recent_prompts(cur):
    res = cur.execute("SELECT prompt FROM images LIMIT 10")
    return (row[0] for row in res.fetchall())


def record_image(cur, img_id, status, prompt, revised_prompt, filename):
    cur.execute(
        "INSERT INTO images VALUES (?, ?, ?, ?, ?, ?)",
        (img_id, int(time.time()), status, prompt, revised_prompt, filename),
    )


def resize_image_for_sign(path, width, height):
    base = os.path.splitext(path)[0]
    out_path = f"{base}.small.jpg"

    if os.path.exists(out_path):
        print(f"{out_path} already exists")
        return

    img = Image.open(path)
    img_w, img_h = img.size

    scale = min(int(img_w / width), int(img_h / height))

    crop_w = width * scale
    crop_h = height * scale
    crop_x = (img_w - crop_w) / 2
    crop_y = (img_h - crop_h) / 2

    print(f"Cropping to ({crop_w}, {crop_h}). Scaling to ({width}, {height}).")

    crop = img.crop((crop_x, crop_y, img_w - crop_x, img_h - crop_y))
    small = crop.resize((width, height))

    small.save(out_path)
    return out_path


if __name__ == '__main__':
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "gen":
        status = args[0]
        api_key = load_api_key()
        con = sqlite3.connect("images.db")
        cur = con.cursor()
        init_db(cur)

        img_id = str(uuid.uuid4())
        prompt_class = DallEPrompt
        system_prompt = generate_system_prompt(prompt_class)
        prompt = prompt_class.parse(get_sign_prompt(api_key, system_prompt, status, recent_prompts=get_most_recent_prompts(cur)))
        print(prompt)

        revised_prompt, img = generate_image(api_key, prompt)
        print(revised_prompt)

        out_file = f"images/{status}.{img_id}.png"

        with open(out_file, "wb") as f:
            f.write(img)

        print(out_file)

        record_image(cur, img_id, status, prompt.dump(), revised_prompt, out_file)

        con.commit()

    elif cmd == "resize":
        path = args[0]
        resize_image_for_sign(path, DISPLAY_WIDTH, DISPLAY_HEIGHT)
