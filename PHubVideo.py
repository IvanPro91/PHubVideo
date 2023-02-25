from bs4 import BeautifulSoup
import requests
import js2py
import re, os
import json
from fp.fp import FreeProxy
import subprocess
import telebot
import sys

TOKEN = ''
bot = telebot.TeleBot(TOKEN)


saveData = {'numCard': 0, 'numList': 0}

class Hub:
    def __init__(self, start_page, search, proxy=None, chat_id=None, limit_size=None):
        self.url = 'https://rt.pornhub.com/video/search?search={0}&page={1}'
        self.origUrl = f'https://rt.pornhub.com'
        self.ev_h_phncdn = 'https://ev-h.phncdn.com/hls'
        self.session = requests.Session()
        self.search = search
        self.chat_id = chat_id
        self.ip = ""
        self.limit_size = limit_size
        self.start_page = start_page
        self.pattern = r"(?:https?:\/\/|ftps?:\/\/|www\.)(?:(?![.,?!;:()]*(?:\s|$))[^\s]){2,}"
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}

    def replace_all(self, text):
        dic = {"/": "", "*": "", "?": "", "<": "", ">": "", "|": "", "\"": "", ":": ""}
        rep = dict((re.escape(k), v) for k, v in dic.items())
        pattern = re.compile("|".join(rep.keys()))
        text = pattern.sub(lambda m: rep[re.escape(m.group(0))], text)
        return text

    def convert_bytes(self, num):
        for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
            if num < 1024.0:
                return "%3.1f %s" % (num, x)
            num /= 1024.0

    def file_size(self, file_path):
        if os.path.isfile(file_path):
            file_info = os.stat(file_path)
            return self.convert_bytes(file_info.st_size)

    def GetVideos(self):
        if self.start_page < saveData['numList']: self.start_page = saveData['numList']
        for i in range(self.start_page, 100):
            if self.start_page > saveData['numList']: saveData['numList'] = self.start_page
            get = self.session.get(self.url.format(self.search, i))
            bs = BeautifulSoup(get.text, "html.parser")

            if get.status_code == 200 and bs.title.text != "Service Unavailable":
                res = bs.find_all('span', {'class': 'title'})
                numCard = 0
                for video in res:
                    numCard += 1
                    if numCard >= saveData['numCard']:
                        view_video = video.find('a', {'href': re.compile("view_video\.php\?viewkey")})
                        if view_video:
                            print(f"{numCard} карточка(и) страница {get.url}")
                            nameVideo = view_video.get('title')
                            href = view_video.get('href')
                            if nameVideo == None:
                                nameVideo = f"video {numCard}"
                            nameVideo = self.replace_all(nameVideo)
                            url = f'{self.origUrl}{href}'
                            self.GetSegmentsVideo(nameVideo, url)
                            saveData['numCard'] = numCard
            else:
                print("-----------------------------------")
                print(get.history)
                print(get.url)
                print(get.cookies)
                print(get.headers)
                print(self.url.format(self.search, i))
                print(bs.title)
                print(get.status_code)
                print(bs.prettify())
                print("-----------------------------------")
    # Получение списка Сегментов из запроса URI
    def GetSegmentsVideo(self, nameVideo, url):
        get = self.session.get(url)
        if get.status_code == 200:
            bs = BeautifulSoup(get.text, "html.parser")
            embed = bs.find(attrs={'property': 'og:video:url'})
            self.GetUrlVideoDownload(nameVideo, embed.get('content'))
        else:
            print(f"Неправильный статус {get.status_code}")

    def GetScriptSuit(self, get):
        soup = BeautifulSoup(get.text, "html.parser")
        script_tag = soup.find_all("script")
        for scripts in script_tag:
            if 'var flashvars' in str(scripts):
                context = js2py.EvalJs()
                js = str(scripts).replace("</script>", "").replace("<script>", "").replace(
                    "utmSource = document.referrer.split('/')[2];", "utmSource = ''")
                js += "console.log(flashvars);"
                context.execute(js)
                information = context.flashvars['mediaDefinitions']
                return information
        return None

    def GetUrlVideoDownload(self, nameVideo, url):
        get = self.session.get(url)

        information = self.GetScriptSuit(get)
        content = json.loads(self.session.get(information[1]['videoUrl']).content)
        file_seg = self.GetUrlContentFile(information[0]['videoUrl'])

        format = content[0]['format']
        quality_file = content[0]['quality']
        videoUrl = '/'.join(str(information[0]['videoUrl']).split('/')[:-1])
        urlSegment = videoUrl + '/' + file_seg[0]
        self.GetSegmentsAndDownload(nameVideo, format, urlSegment, videoUrl)

    def GetSegPart(self, SegmentContent):
        pattern = re.findall(
            r"\w+-\d{1,10}-\w\d{1,10}-\w\d{1,10}.\w+\?\w+=\d{1,40}&\w+=\d{1,40}&\w+=\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}&\w+=.*",
            SegmentContent)
        self.ip = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", pattern[0])[0]
        return pattern

    def SendMediaFile(self, filename):
        command = f'ffmpeg -y -i "{filename}" -vcodec copy -acodec copy "bit_{filename}"'
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        process.wait()

        os.remove(filename)
        newFilename = f"bit_{filename}"
        if self.chat_id:
            # Тут отправка в телеграмм бот
            video = open(newFilename, 'rb')
            bot.send_video(self.chat_id, video)


    def GetSegmentsAndDownload(self, nameVideo, format, urlSegment, videoUrl):
        SegmentContent = self.session.get(urlSegment)
        listSegment = self.GetSegPart(SegmentContent.text)
        CountLines = len(listSegment)
        sizeFile = CountLines * 377181
        if sizeFile < self.limit_size:
            num = 0
            fFile = b''
            for lineSegment in listSegment:
                urlPartSegment = f"{videoUrl}/{lineSegment}"
                get = self.session.get(urlPartSegment)
                if get.status_code == 200:
                    num += 1
                    print(f'{num} / {CountLines}', urlPartSegment)
                    fFile += get.content
                else:
                    print("Плохой статус")
            MathTimeVideo = 3.99 * (CountLines / 60)
            print(f"Закончили скачивание время видео ~ {MathTimeVideo}")
            fFiles = open(f'{nameVideo}.{format}', 'wb')
            fFiles.write(fFile)
            fFiles.close()
            filename = f'{nameVideo}.{format}'
            self.SendMediaFile(filename)
        else:
            print(f"Пропускаем из-за размера видео ~ {sizeFile}")

    def GetUrlContentFile(self, url):
        result = []
        file_seg = self.session.get(url)
        for line in file_seg.iter_lines():
            indexV1a1 = line.decode('utf-8')
            if '#' not in indexV1a1:
                result.append(indexV1a1)
        return result

def main():
    try:
        proxy = FreeProxy(https=False).get()
        h = Hub(start_page=1, search='homevideo', proxy=proxy, chat_id=293720526, limit_size=50000000)
        h.GetVideos()
    except Exception as err:
        print(err)
        main()

main()