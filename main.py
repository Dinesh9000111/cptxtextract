import os
import sys
import re
import json
import asyncio
import logging
import requests
import subprocess
import datetime
from logging.handlers import RotatingFileHandler

from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyromod import listen

import helper
import tgcrypto
from details import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, SUDO_USERS, CHANNEL_ID
from utils import get_datetime_str, create_html_file

api = 'https://api.classplusapp.com/v2'

def create_html_file(file_name, batch_name, contents):
    tbody = ''
    parts = contents.split('\n')
    for part in parts:
        split_part = [item.strip() for item in part.split(':', 1)]

        text = split_part[0] if split_part[0] else 'Untitled'
        url = split_part[1].strip() if len(split_part) > 1 and split_part[1].strip() else 'No URL'

        tbody += f'<tr><td>{text}</td><td><a href="{url}" target="_blank">{url}</a></td></tr>'

    with open('cptxtextract/template.html', 'r') as fp:
        file_content = fp.read()
    title = batch_name.strip()
    with open(file_name, 'w') as fp:
        fp.write(file_content.replace('{{tbody_content}}', tbody).replace('{{batch_name}}', title))

def get_course_content(session, course_id, folder_id=0):
    fetched_contents = ""

    params = {
        'courseId': course_id,
        'folderId': folder_id,
    }

    res = session.get(f'{api}/course/content/get', params=params)

    if res.status_code == 200:
        res_json = res.json()
        contents = res_json.get('data', {}).get('courseContent', [])

        for content in contents:
            if content['contentType'] == 1:
                resources = content.get('resources', {})

                if resources.get('videos') or resources.get('files'):
                    sub_contents = get_course_content(session, course_id, content['id'])
                    fetched_contents += sub_contents

            elif content['contentType'] == 2:
                name = content.get('name', '')
                id = content.get('contentHashId', '')

                headers = {
                    "Host": "api.classplusapp.com",
                    "x-access-token": session.headers.get('x-access-token', ''),
                    "User-Agent": "Mobile-Android",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://web.classplusapp.com",
                    "Referer": "https://web.classplusapp.com/",
                    "Region": "IN",
                }

                params = {'contentId': id}

                r = session.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                if r.status_code == 200:
                    url = r.json().get('url', '')
                    if url:
                        content = f'{name}:{url}\n'
                        fetched_contents += content
            else:
                name = content.get('name', '')
                url = content.get('url', '')
                content = f'{name}:{url}\n'
                fetched_contents += content

    return fetched_contents

async def classplus_txt(app, message):
    headers2 = {
        "Api-Version": "43",
        "Content-Type": "application/json;charset=UTF-8",
        "Device-Id": "1706954623055",
        "Origin": "https://web.classplusapp.com",
        "Referer": "https://web.classplusapp.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    try:
        input = await app.ask(message.chat.id, text="SEND YOUR CREDENTIALS:\n\nORGANISATION CODE:\nPHONE NUMBER:\nOR\nACCESS TOKEN:")

        creds = input.text
        session = requests.Session()
        session.headers.update(headers2)

        logged_in = False

        if '\n' in creds:
            org_code, phone_no = [cred.strip() for cred in creds.split('\n')]

            if org_code.isalpha() and phone_no.isdigit() and len(phone_no) == 10:
                res = session.get(f'{api}/orgs/{org_code}')
                if res.status_code == 200:
                    res = res.json()
                    org_id = int(res['data']['orgId'])

                    data = {
                        'countryExt': '91',
                        'mobile': phone_no,
                        'orgCode': org_code,
                        'orgId': org_id,
                        'viaSms': 1,
                    }

                    res = session.post(f'{api}/otp/generate', data=json.dumps(data))
                    if res.status_code == 200:
                        res = res.json()
                        session_id = res['data']['sessionId']

                        user_otp = await app.ask(message.chat.id, text="Send your OTP:")

                        if user_otp.text.isdigit():
                            otp = user_otp.text.strip()

                            data = {
                                "otp": otp,
                                "countryExt": "91",
                                "sessionId": session_id,
                                "orgId": org_id,
                                "mobile": phone_no
                            }

                            res = session.post(f'{api}/users/verify', data=json.dumps(data))
                            res_json = res.json()

                            if res_json.get('status') == 'success':
                                await app.send_message(message.chat.id, res_json)
                                user_id = res_json['data']['user']['id']
                                token = res_json['data']['token']
                                session.headers['x-access-token'] = token

                                await message.reply_text(f"Your access token:\n\n{token}")
                                logged_in = True
                            else:
                                error_message = res_json.get('message', 'Failed to verify OTP.')
                                raise Exception(f"OTP Verification Failed: {error_message}")
                        else:
                            raise Exception('Invalid OTP format. Only digits are allowed.')
                    else:
                        raise Exception('Failed to generate OTP.')
                else:
                    raise Exception('Invalid Organisation Code.')
            else:
                raise Exception('Invalid Credentials format.')

        else:
            token = creds.strip()
            session.headers['x-access-token'] = token

            res = session.get(f'{api}/users/details')
            if res.status_code == 200:
                res = res.json()
                user_id = res['data']['responseData']['user']['id']
                logged_in = True
            else:
                raise Exception('Failed to fetch user details.')

        if logged_in:
            params = {
                'userId': user_id,
                'tabCategoryId': 3
            }

            res = session.get(f'{api}/profiles/users/data', params=params)
            if res.status_code == 200:
                res = res.json()
                courses = res['data']['responseData']['coursesData']

                if courses:
                    text = ''
                    for idx, course in enumerate(courses):
                        name = course['name']
                        text += f'{idx+1}. {name}\n'

                    num = await app.ask(message.chat.id, text=f"Send course number to extract:\n\n{text}")
                    if num.text.isdigit() and (1 <= int(num.text.strip()) <= len(courses)):
                        selected = int(num.text.strip()) - 1
                        selected_course = courses[selected]

                        selected_course_id = selected_course['id']
                        selected_course_name = selected_course['name']

                        msg = await message.reply_text("Extracting Course...")

                        course_content = get_course_content(session, selected_course_id)
                        await msg.delete()

                        if course_content:
                            caption = f"App Name: Classplus\nBatch Name: {selected_course_name}"

                            text_file = "Classplus"
                            with open(f"{text_file}.txt", 'w') as f:
                                f.write(course_content)

                            await app.send_document(message.chat.id, f"{text_file}.txt", caption=caption)

                            html_file = f"{text_file}.html"
                            create_html_file(html_file, selected_course_name, course_content)
                            await app.send_document(message.chat.id, html_file, caption=caption)

                            os.remove(f"{text_file}.txt")
                            os.remove(html_file)
                        else:
                            raise Exception('No Content Found in Course.')
                    else:
                        raise Exception('Invalid Course Selection.')
                else:
                    raise Exception('No Courses Found.')
            else:
                raise Exception('Failed to fetch Courses.')

    except Exception as e:
        await message.reply_text(f"Error: {e}")
        print(f"Error: {e}")

# Telegram Bot Setup
app = Client(
    "classplus_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_import os
import sys
import re
import json
import asyncio
import logging
import requests
import subprocess
import datetime
from logging.handlers import RotatingFileHandler

from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyromod import listen

import helper
import tgcrypto
from details import API_ID, API_HASH, BOT_TOKEN, OWNER_ID, SUDO_USERS, CHANNEL_ID
from utils import get_datetime_str, create_html_file

api = 'https://api.classplusapp.com/v2'

def create_html_file(file_name, batch_name, contents):
    tbody = ''
    parts = contents.split('\n')
    for part in parts:
        split_part = [item.strip() for item in part.split(':', 1)]

        text = split_part[0] if split_part[0] else 'Untitled'
        url = split_part[1].strip() if len(split_part) > 1 and split_part[1].strip() else 'No URL'

        tbody += f'<tr><td>{text}</td><td><a href="{url}" target="_blank">{url}</a></td></tr>'

    with open('cptxtextract/template.html', 'r') as fp:
        file_content = fp.read()
    title = batch_name.strip()
    with open(file_name, 'w') as fp:
        fp.write(file_content.replace('{{tbody_content}}', tbody).replace('{{batch_name}}', title))

def get_course_content(session, course_id, folder_id=0):
    fetched_contents = ""

    params = {
        'courseId': course_id,
        'folderId': folder_id,
    }

    res = session.get(f'{api}/course/content/get', params=params)

    if res.status_code == 200:
        res_json = res.json()
        contents = res_json.get('data', {}).get('courseContent', [])

        for content in contents:
            if content['contentType'] == 1:
                resources = content.get('resources', {})

                if resources.get('videos') or resources.get('files'):
                    sub_contents = get_course_content(session, course_id, content['id'])
                    fetched_contents += sub_contents

            elif content['contentType'] == 2:
                name = content.get('name', '')
                id = content.get('contentHashId', '')

                headers = {
                    "Host": "api.classplusapp.com",
                    "x-access-token": session.headers.get('x-access-token', ''),
                    "User-Agent": "Mobile-Android",
                    "Accept": "application/json, text/plain, */*",
                    "Origin": "https://web.classplusapp.com",
                    "Referer": "https://web.classplusapp.com/",
                    "Region": "IN",
                }

                params = {'contentId': id}

                r = session.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                if r.status_code == 200:
                    url = r.json().get('url', '')
                    if url:
                        content = f'{name}:{url}\n'
                        fetched_contents += content
            else:
                name = content.get('name', '')
                url = content.get('url', '')
                content = f'{name}:{url}\n'
                fetched_contents += content

    return fetched_contents

async def classplus_txt(app, message):
    headers2 = {
        "Api-Version": "43",
        "Content-Type": "application/json;charset=UTF-8",
        "Device-Id": "1706954623055",
        "Origin": "https://web.classplusapp.com",
        "Referer": "https://web.classplusapp.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    }

    try:
        input = await app.ask(message.chat.id, text="SEND YOUR CREDENTIALS:\n\nORGANISATION CODE:\nPHONE NUMBER:\nOR\nACCESS TOKEN:")

        creds = input.text
        session = requests.Session()
        session.headers.update(headers2)

        logged_in = False

        if '\n' in creds:
            org_code, phone_no = [cred.strip() for cred in creds.split('\n')]

            if org_code.isalpha() and phone_no.isdigit() and len(phone_no) == 10:
                res = session.get(f'{api}/orgs/{org_code}')
                if res.status_code == 200:
                    res = res.json()
                    org_id = int(res['data']['orgId'])

                    data = {
                        'countryExt': '91',
                        'mobile': phone_no,
                        'orgCode': org_code,
                        'orgId': org_id,
                        'viaSms': 1,
                    }

                    res = session.post(f'{api}/otp/generate', data=json.dumps(data))
                    if res.status_code == 200:
                        res = res.json()
                        session_id = res['data']['sessionId']

                        user_otp = await app.ask(message.chat.id, text="Send your OTP:")

                        if user_otp.text.isdigit():
                            otp = user_otp.text.strip()

                            data = {
                                "otp": otp,
                                "countryExt": "91",
                                "sessionId": session_id,
                                "orgId": org_id,
                                "mobile": phone_no
                            }

                            res = session.post(f'{api}/users/verify', data=json.dumps(data))
                            res_json = res.json()

                            if res_json.get('status') == 'success':
                                await app.send_message(message.chat.id, res_json)
                                user_id = res_json['data']['user']['id']
                                token = res_json['data']['token']
                                session.headers['x-access-token'] = token

                                await message.reply_text(f"Your access token:\n\n{token}")
                                logged_in = True
                            else:
                                error_message = res_json.get('message', 'Failed to verify OTP.')
                                raise Exception(f"OTP Verification Failed: {error_message}")
                        else:
                            raise Exception('Invalid OTP format. Only digits are allowed.')
                    else:
                        raise Exception('Failed to generate OTP.')
                else:
                    raise Exception('Invalid Organisation Code.')
            else:
                raise Exception('Invalid Credentials format.')

        else:
            token = creds.strip()
            session.headers['x-access-token'] = token

            res = session.get(f'{api}/users/details')
            if res.status_code == 200:
                res = res.json()
                user_id = res['data']['responseData']['user']['id']
                logged_in = True
            else:
                raise Exception('Failed to fetch user details.')

        if logged_in:
            params = {
                'userId': user_id,
                'tabCategoryId': 3
            }

            res = session.get(f'{api}/profiles/users/data', params=params)
            if res.status_code == 200:
                res = res.json()
                courses = res['data']['responseData']['coursesData']

                if courses:
                    text = ''
                    for idx, course in enumerate(courses):
                        name = course['name']
                        text += f'{idx+1}. {name}\n'

                    num = await app.ask(message.chat.id, text=f"Send course number to extract:\n\n{text}")
                    if num.text.isdigit() and (1 <= int(num.text.strip()) <= len(courses)):
                        selected = int(num.text.strip()) - 1
                        selected_course = courses[selected]

                        selected_course_id = selected_course['id']
                        selected_course_name = selected_course['name']

                        msg = await message.reply_text("Extracting Course...")

                        course_content = get_course_content(session, selected_course_id)
                        await msg.delete()

                        if course_content:
                            caption = f"App Name: Classplus\nBatch Name: {selected_course_name}"

                            text_file = "Classplus"
                            with open(f"{text_file}.txt", 'w') as f:
                                f.write(course_content)

                            await app.send_document(message.chat.id, f"{text_file}.txt", caption=caption)

                            html_file = f"{text_file}.html"
                            create_html_file(html_file, selected_course_name, course_content)
                            await app.send_document(message.chat.id, html_file, caption=caption)

                            os.remove(f"{text_file}.txt")
                            os.remove(html_file)
                        else:
                            raise Exception('No Content Found in Course.')
                    else:
                        raise Exception('Invalid Course Selection.')
                else:
                    raise Exception('No Courses Found.')
            else:
                raise Exception('Failed to fetch Courses.')

    except Exception as e:
        await message.reply_text(f"Error: {e}")
        print(f"Error: {e}")

# Telegram Bot Setup
app = Client(
    "classplus_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text("Hello! Send your Classplus credentials to proceed.")

@app.on_message(filters.command("classplus") & filters.private)
async def handle_classplus(client, message):
    await classplus_txt(client, message)

if __name__ == "__main__":
    app.start()
    print("Bot is Running...")
    idle()
    app.stop()text("Hello! Send your Classplus credentials to proceed.")

@app.on_message(filters.command("classplus") & filters.private)
async def handle_classplus(client, message):
    await classplus_txt(client, message)

if __name__ == "__main__":
    app.start()
    print("Bot is Running...")
    idle()
    app.stop()
