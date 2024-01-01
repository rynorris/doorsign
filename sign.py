import base64
import requests
import sqlite3
import sys
import time
import uuid


GPT_4_TURBO = "gpt-4-1106-preview"

SIGN_SYSTEM_PROMPT = """
You are a key part of a system which generates images to display on the sign on the door of a software engineer's office.

The office can be in several states such as DEEP_FOCUS, CHILLING or IN_A_MEETING.

Your role is to generate a text prompt to be sent to an AI image-generation model, in order to generate an image which effectively communicates the current office status.
You should ensure that the images are creative and interesting. For example by using animals, robots, or anthropomorphised objects rather than humans.

For example, for IN_A_MEETING, you might generate a prompt "Robots of all shapes and sizes, sitting around a table in a board room. Watercolor."
Or for "CHILLING", you might generate a prompt "Kangaroo sunbathing on a beatiful beach. Photorealistic."
Or for "DEEP_FOCUS", you might generate a prompt "Anthropomorphic spoon in deep focus writing code on a laptop made of toast. Detailed pixar-style 3D animation."

You MUST reply with ONLY the image generation prompt and NOTHING else. Your output will be passed directly into the image generation model.
"""


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
    resp.raise_for_status()
    return resp.json()


def chat_completion(api_key, model, messages):
    data = openai_request(api_key, "/v1/chat/completions", body={"model": model, "messages": messages})
    return data["choices"][0]["message"]["content"]


def generate_image(api_key, prompt):
    body = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": "1792x1024",
        "n": 1,
        "response_format": "b64_json",
    }
    data = openai_request(api_key, "/v1/images/generations", body)
    img = data["data"][0]
    return (img["revised_prompt"], base64.b64decode(img["b64_json"]))


def get_sign_prompt(api_key, status, recent_prompts=None):
    messages = [
        {"role": "system", "content": SIGN_SYSTEM_PROMPT},
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


if __name__ == '__main__':
    STATUS = sys.argv[1]
    API_KEY = load_api_key()
    con = sqlite3.connect("images.db")
    cur = con.cursor()
    init_db(cur)

    img_id = str(uuid.uuid4())
    prompt = get_sign_prompt(API_KEY, STATUS, recent_prompts=get_most_recent_prompts(cur))
    print(prompt)

    revised_prompt, img = generate_image(API_KEY, prompt)
    print(revised_prompt)

    out_file = f"{STATUS}.{img_id}.png"

    with open(out_file, "wb") as f:
        f.write(img)

    print(out_file)

    record_image(cur, img_id, STATUS, prompt, revised_prompt, out_file)

    con.commit()
