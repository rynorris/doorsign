import base64
from dataclasses import dataclass, asdict
import json
import requests
import sqlite3
import sys
import time
import uuid


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

DALLE_SYSTEM_PROMPT = """
You are a key part of a system which generates images to display on the sign on the door of a software engineer's office.

The office can be in several states such as DEEP_FOCUS, CHILLING or IN_A_MEETING.

Your role is to generate a text prompt to be sent to an AI image-generation model, in order to generate an image which effectively communicates the current office status.
You should ensure that the images are creative and interesting. For example by using animals, robots, or anthropomorphised objects rather than humans.

For example, for IN_A_MEETING, you might generate a prompt "Robots of all shapes and sizes, sitting around a table in a board room. Watercolor."
Or for "CHILLING", you might generate a prompt "Kangaroo sunbathing on a beatiful beach. Photorealistic."
Or for "DEEP_FOCUS", you might generate a prompt "Anthropomorphic spoon in deep focus writing code on a laptop made of toast. Detailed pixar-style 3D animation."

You MUST reply with ONLY the image generation prompt and NOTHING else. Your output will be passed directly into the image generation model.
"""


SD_SYSTEM_PROMPT = """
You are a key part of a system which generates images to display on the sign on the door of a software engineer's office.

The office can be in several states such as DEEP_FOCUS, CHILLING or IN_A_MEETING.

Your role is to generate a text prompt to be sent to the AI image-generation model stablediffusion, in order to generate an image which effectively communicates the current office status.
You should ensure that the images are creative and interesting. For example by using animals, robots, or anthropomorphised objects rather than humans.

For example, for IN_A_MEETING, you might generate a prompt "Robots of all shapes and sizes, sitting around a table in a board room. Watercolor."
Or for "CHILLING", you might generate a prompt "Kangaroo sunbathing on a beatiful beach. Photorealistic."
Or for "DEEP_FOCUS", you might generate a prompt "Anthropomorphic spoon in deep focus writing code on a laptop made of toast. Detailed pixar-style 3D animation."

You MUST reply with a JSON object containing two fields:
    - "prompt" - the positive prompt for the image generation, it should include a brief description of the scene followed by a comma-separated list of keywords to nudge the generation model in the right direction. This could include things such as medium, style, artist, color, lighting, resolution, etc.
    - "negativePrompt" - the negative prompt for the image generation

Examples:
{
  "prompt": "seascape by Ray Collins and artgerm, front view of a perfect wave, sunny background, ultra detailed water, 4k resolution",
  "negativePrompt": "low resolution, low details, blurry, clouds"
}

{
  "prompt": "Cute small cat sitting in a movie theater eating chicken wiggs watching a movie ,unreal engine, cozy indoor lighting, artstation, detailed, digital painting,cinematic,character design by mark ryden and pixar and hayao miyazaki, unreal 5, daz, hyperrealistic, octane render",
  "negativePrompt": "ugly, ugly arms, ugly hands"
}

{
  "prompt": "High quality 8K painting impressionist style of a Japanese modern city street with a girl on the foreground wearing a traditional wedding dress with a fox mask, staring at the sky, daylight",
  "negativePrompt": "blur, cars, low quality"
}

{
  "prompt": "Cute small Fox sitting in a movie theater eating popcorn watching a movie ,unreal engine, cozy indoor lighting, artstation, detailed, digital painting,cinematic,character design by mark ryden and pixar and hayao miyazaki, unreal 5, daz, hyperrealistic, octane render",
  "negativePrompt": "ugly, ugly arms, ugly hands"
}

{
  "prompt": "cute toy owl made of suede, geometric accurate, relief on skin, plastic relief surface of body, intricate details, cinematic",
  "negativePrompt": "ugly, ugly arms, ugly hands, ugly teeth, ugly nose, ugly mouth, ugly eyes, ugly ears"
}
"""


@dataclass
class DallEPrompt:
    prompt: str

    @classmethod
    def parse(cls, json_string: str) -> "DallEPrompt":
        return cls(**json.loads(json_string))

    @staticmethod
    def description():
        return "a JSON object containing one field:\n  - \"prompt\": a brief description of the scene, along with hints as to desired style, medium, lighting, etc."

    @staticmethod
    def examples():
        return [
            ("IN_A_MEETING", DallEPrompt("Robots of all shapes and sizes, sitting around a table in a board room. Watercolor.")),
            ("CHILLING", DallEPrompt("Kangaroo sunbathing on a beautiful beach. Photorealistic.")),
            ("DEEP_FOCUS", DallEPrompt("Anthropomorphic spoon in deep focus, writing code on a laptop made of toast. Detailed pixar-style 3D animation.")),
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
    examples = "\n".join(["{0} -> {1}".format(inp, json.dumps(asdict(out))) for [inp, out] in prompt_class.examples()])
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


def resize_image_for_sign(path):
    from PIL import Image
    img = Image.open(path)
    crop = img.crop((96, 32, 1792-96, 1024-32))
    small = crop.resize((800, 480))

    base = os.path.splitext(os.path.basename(path))[0]
    out_path = f"{base}.small.jpg"
    small.save(out_path)
    return out_path


if __name__ == '__main__':
    STATUS = sys.argv[1]
    API_KEY = load_api_key()
    con = sqlite3.connect("images.db")
    cur = con.cursor()
    init_db(cur)

    img_id = str(uuid.uuid4())
    prompt_class = DallEPrompt
    system_prompt = generate_system_prompt(prompt_class)
    prompt = prompt_class.parse(get_sign_prompt(API_KEY, system_prompt, STATUS, recent_prompts=get_most_recent_prompts(cur)))
    print(prompt)

    revised_prompt, img = generate_image(API_KEY, prompt)
    print(revised_prompt)

    out_file = f"{STATUS}.{img_id}.png"

    with open(out_file, "wb") as f:
        f.write(img)

    print(out_file)

    record_image(cur, img_id, STATUS, prompt.prompt, revised_prompt, out_file)

    con.commit()
