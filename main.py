import json
import asyncio
import logging
from aiohttp import ClientSession
from pyrogram import Client, filters
from pyrogram.types import Message
from logging.handlers import RotatingFileHandler
import os
from details import api_id, api_hash, bot_token, auth_users, sudo_user, log_channel, txt_channel
from utils import get_datetime_str, create_html_file

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler(
            "log.txt", maxBytes=5000000, backupCount=10
        ),
        logging.StreamHandler(),
    ],
)

bot = Client(
    "bot",
    api_id=24692763,
    api_hash="8e3840420e9d0895db3231d87c6d21a5",
    bot_token="7601280525:AAGK3HTLou0IzpTG1I2GShX0baxei4NExpc"
)

async def get_course_content(session, course_id, folder_id=0):
    fetched_contents = []
    params = {'courseId': course_id, 'folderId': folder_id}
    async with session.get(f'{api}/course/content/get', params=params) as res:
        if res.status == 200:
            res_json = await res.json()
            contents = res_json['data']['courseContent']
            for content in contents:
                if content['contentType'] == 1:
                    resources = content['resources']
                    if resources['videos'] or resources['files']:
                        sub_contents = await get_course_content(session, course_id, content['id'])
                        fetched_contents += sub_contents
                else:
                    name = content['name']
                    url = content['url']
                    fetched_contents.append(f'{name}: {url}')
    return fetched_contents

@bot.on_message(filters.command(["start"]))
async def start(bot, update):
    await update.reply_text("Hi I am **Classplus txt Downloader**.\n\n"
                             "**NOW:-** Press **/classplus** to continue..\n\n")

@bot.on_message(filters.command(["classplus"]))
async def account_login(bot: Client, m: Message):
    session = ClientSession()
    headers = {
        'accept-encoding': 'gzip',
        'accept-language': 'EN',
        'api-version': '35',
        'app-version': '1.4.73.2',
        'build-number': '35',
        'connection': 'Keep-Alive',
        'content-type': 'application/json',
        'device-details': 'Xiaomi_Redmi 7_SDK-32',
        'device-id': 'c28d3cb16bbdac01',
        'host': 'api.classplusapp.com',
        'region': 'IN',
        'user-agent': 'Mobile-Android',
        'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c'
    }
    api = 'https://api.classplusapp.com/v2'
    
    try:
        reply = await m.reply(
            '**Send your credentials as shown below.\n\n'
            'Organisation Code\nPhone Number\n\n'
            'OR\n\n'
            'Access Token**'
        )

        creds = await bot.listen(m.chat.id)

        # Process credentials
        if '\n' in creds.text:
            org_code, phone_no = [cred.strip() for cred in creds.text.split('\n')]
            if org_code.isalpha() and phone_no.isdigit() and len(phone_no) == 10:
                async with session.get(f'{api}/orgs/{org_code}') as res:
                    if res.status == 200:
                        org_data = await res.json()
                        org_id = org_data['data']['orgId']
                        data = {
                            'countryExt': '91',
                            'mobile': phone_no,
                            'viaSms': 1,
                            'orgId': org_id,
                            'eventType': 'login',
                            'otpHash': 'j7ej6eW5VO'
                        }
                        async with session.post(f'{api}/otp/generate', json=data) as res:
                            if res.status == 200:
                                otp_data = await res.json()
                                session_id = otp_data['data']['sessionId']
                                await bot.send_message(
                                    m.chat.id, '**Send OTP?**', reply_to_message_id=reply.id
                                )
                                otp_reply = await bot.listen(m.chat.id)
                                if otp_reply.text.isdigit():
                                    otp = otp_reply.text.strip()
                                    verification_data = {
                                        'otp': otp,
                                        'sessionId': session_id,
                                        'orgId': org_id,
                                        'fingerprintId': 'a3ee05fbde3958184f682839be4fd0f7',
                                        'countryExt': '91',
                                        'mobile': phone_no,
                                    }
                                    async with session.post(f'{api}/users/verify', json=verification_data) as res:
                                        if res.status == 200:
                                            user_data = await res.json()
                                            token = user_data['data']['token']
                                            session.headers['x-access-token'] = token
                                            await bot.send_message(
                                                m.chat.id,
                                                f'Your Access Token for future use - \n\n<pre>{token}</pre>',
                                                reply_to_message_id=reply.id
                                            )
                                else:
                                    raise Exception('Failed to validate OTP.')
                            else:
                                raise Exception('Failed to generate OTP.')
                    else:
                        raise Exception('Failed to get organization Id.')
                else:
                    raise Exception('Failed to validate credentials.')

        else:
            token = creds.text.strip()
            session.headers['x-access-token'] = token

            async with session.get(f'{api}/users/details') as res:
                if res.status == 200:
                    user_data = await res.json()
                    user_id = user_data['data']['responseData']['user']['id']
                else:
                    raise Exception('Failed to get user details.')

        # Fetch courses
        params = {'userId': user_id, 'tabCategoryId': 3}
        async with session.get(f'{api}/profiles/users/data', params=params) as res:
            if res.status == 200:
                courses_data = await res.json()
                courses = courses_data['data']['responseData']['coursesData']
                if courses:
                    text = ''
                    for cnt, course in enumerate(courses):
                        text += f'{cnt + 1}. {course["name"]}\n'

                    await bot.send_message(
                        m.chat.id, f'**Send index number of the course to download.**\n\n{text}',
                        reply_to_message_id=reply.id
                    )
                    course_reply = await bot.listen(m.chat.id)

                    if course_reply.text.isdigit() and int(course_reply.text) <= len(courses):
                        selected_course = courses[int(course_reply.text) - 1]
                        course_id = selected_course['id']
                        course_name = selected_course['name']
                        loader = await bot.send_message(
                            m.chat.id, '**Extracting course...**', reply_to_message_id=reply.id
                        )

                        course_content = await get_course_content(session, course_id)
                        await loader.delete()

                        if course_content:
                            caption = f'**App Name: Classplus\nBatch Name: {course_name}**'
                            text_file = f'assets/{get_datetime_str()}.txt'
                            with open(text_file, 'w') as file:
                                file.writelines(course_content)

                            await bot.send_document(
                                m.chat.id, text_file, caption=caption,
                                file_name=f"{course_name}.txt", reply_to_message_id=reply.id
                            )

                            html_file = f'assets/{get_datetime_str()}.html'
                            create_html_file(html_file, course_name, course_content)

                            await bot.send_document(
                                m.chat.id, html_file, caption=caption,
                                file_name=f"{course_name}.html", reply_to_message_id=reply.id
                            )

                            os.remove(text_file)
                            os.remove(html_file)
                        else:
                            raise Exception('No content found in the course.')
                    else:
                        raise Exception('Invalid course selection.')
                else:
                    raise Exception('No courses found.')
            else:
                raise Exception('Failed to fetch courses.')

    except Exception as e:
        await bot.send_message(m.chat.id, f'**Error: {str(e)}**', reply_to_message_id=reply.id)
        LOGGER.error(f"Error: {str(e)}")

    finally:
        await session.close()

bot.run()
