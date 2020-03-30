#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# A simple chat client for matrix.
# This sample will allow you to connect to a room, and send/recieve messages.
# Args: host:port username password room
# Error Codes:
# 1 - Unknown problem has occured
# 2 - Could not find the server.
# 3 - Bad URL Format.
# 4 - Bad username/password.
# 11 - Wrong room format.
# 12 - Couldn't find room.

import sys
import logging
import time
import datetime
import json
import os
import re
import requests
from io import BytesIO
import traceback
import matrix_bot_api as mba
import matrix_bot_logic as mbl
import config as conf
from matrix_client.api import MatrixRequestError
from imapclient import IMAPClient
import ssl
import email
from email.header import decode_header

client=None

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

def init(log,server,login,passwd,maildir="inbox", check_cert=False):
  global client
  log.debug("start function")
  try:
    if check_cert==False:
      ssl_context = ssl.create_default_context()
      # don't check if certificate hostname doesn't match target hostname
      ssl_context.check_hostname = False
      # don't check if the certificate is trusted by a certificate authority
      ssl_context.verify_mode = ssl.CERT_NONE
      client = IMAPClient(host=server,ssl_context=ssl_context)
    else:
      client = IMAPClient(host=server)
    client.login(login,passwd)
    client.select_folder(maildir,readonly=True)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return client

def send_new_notify(log,matrix_client,matrix_room,last_email_timestamp, last_email_message_id, server, login, passwd, mailbox="inbox", redmine_sender="redmine@corp.com"):
  log.debug("start function")
  result={}
  result["last_email_timestamp"]=last_email_timestamp
  result["last_email_message_id"]=last_email_message_id
  try:
    client=init(log,server,login,passwd,mailbox, check_cert=False)
    if client == None:
      log.error("mail init(server=%s, email=%s, mailbox=%s)"%(server,login,mailbox))
      return None

    log.debug("try search today email from %s"%redmine_sender)
    messages = client.search([u'SINCE', datetime.datetime.now(),'FROM',redmine_sender],'utf8')
    for uid, message_data in client.fetch(messages, 'RFC822').items():
      log.debug("proccess email with uid=%d"%uid)
      email_message = email.message_from_bytes(message_data[b'RFC822'])

      subj_encoded=decode_header(email_message.get('Subject'))
      subj=subj_encoded[0][0].decode(subj_encoded[0][1])

      message_id=decode_header(email_message.get('Message-ID'))[0][0]
      date_str=decode_header(email_message.get('Date'))[0][0]
      date_dt=datetime.datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
      message_unix_time=time.mktime(date_dt.timetuple())

      if message_unix_time == last_email_timestamp and message_id == last_email_message_id:
        # скорее всего то же самое письмо, что отправляли в прошлый раз последним - пропускаем.
        # эта проверка нужна т.к. теоритически могут быть письма с тем же временем получения,
        # но не отправленные в прошлый раз. Или отправленные, но тогда они отправятся ещё раз :-(
        # но это лучше, чем если бы они не отправились бы вообще. Т.к. вероятность этого мала, то смысла
        # городить (и запоминать) список message_id-ов нет.
        log.debug("skip previowse last sended email")
        continue
      if message_unix_time < last_email_timestamp:
        # пропускаем более старые сообщения
        log.debug("skip older emails before previowse last sended email")
        continue

      # обрабатываем более новые сообщения:
      # получаем телос сообщения:
      if email_message.is_multipart():
        for part in email_message.walk():
          ctype = part.get_content_type()
          cdispo = str(part.get('Content-Disposition'))

          # skip any text/plain (txt) attachments
          if ctype == 'text/plain' and 'attachment' not in cdispo:
            body = part.get_payload(decode=True)  # decode
            break
      # not multipart - i.e. plain text, no attachments, keeping fingers crossed
      else:
          body = email_message.get_payload(decode=True)

      decripted_body=body.decode('utf8')
      # отправляем пользователю сообщение:
      # переформатируем почтовое сообщение в нужное сообщение матрицы (оставляем нужную информацию):
      result_matrix_text=email_message_to_matrix(log,decripted_body)
      if mba.send_html(log, matrix_client, matrix_room,result_matrix_text) == False:
        log.error("mba.send_message()")
        return None

      # сохраняем последние данные сообщения:
      result["last_email_timestamp"]=message_unix_time
      result["last_email_message_id"]=message_id

  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None
  return result

def email_message_to_matrix(log,email_body):
  log.debug("start function")

  max_comment_size=200

  # делим на блоки:
  blocks=email_body.split('---------------------------------------')
  # формируем описание:
  summary=""
  summary_block=blocks[0]
  summary_list=summary_block.split('\n')
  # берём заголовок:
  regex=re.match('(.*)(#+)([0-9]+)(.*)', summary_list[0])
  if regex != None:
    summary=regex.group(1)
    summary+="%s/issues/%s"%(conf.redmine_server, regex.group(3))
    summary+=regex.group(4)
    summary+='<br>'

  comment=""
  # берём текст комментария:
  for item in summary_list[1:]:
    line=item.strip()
    if line == "\n" or line == "":
      continue
    else:
      print("item='%s'"%item)
      comment+=line
      comment+='<br>'
  comment=comment.strip()
  # обкусываем длинные комментарии:
  if len(comment)>max_comment_size:
    comment=comment[0:max_comment_size]+"..."

  # заменяем форматирование кодовых вставок:
  if '```' in comment:
    while True:
      if '```' in comment:
        comment=comment.replace('```','<pre>',1)
      if '```' in comment:
        comment=comment.replace('```','</pre>',1)
      if '```' not in comment:
        break
  if "<pre>" in comment and "</pre>" not in comment:
    comment+="</pre>"

  print("summary=",summary)
  print("comment=",comment)

  # формируем тело сообщения:
  main_text=""
  main_text_block=blocks[1]
  main_text_list=main_text_block.split('\n')
  descr=""
  priority=""
  assigned=""
  for item in main_text_list:
    line=item.strip()
    if "Ошибка #" in line:
      descr=re.sub('^Ошибка #[0-9]+: ','', line).strip()
      continue
    elif "Приоритет: " in line:
      priority=re.sub('^\* Приоритет: ','', line).strip()
      continue
    elif "Назначена: " in line:
      assigned=re.sub('^\* Назначена: ','', line).strip()
      continue
  
  result=""
  result=summary+"<br>"
  if assigned != "":
    result+="<strong>Назначена</strong>: "+assigned + "<br>"
  result+="<strong>Описание</strong>: "+descr + "<br>"
  result+="<strong>Комментарий:</strong> "+comment 
  #result+="\nПриоритет: "+priority
  return result


def get_today_redmine_emails(log,client,redmine_sender="redmine@corp.com"):
  try:
    #messages = client.search(['NOT', 'DELETED'])
    #messages = client.search('UNSEEN')
    #messages = client.search([u'SINCE', datetime(2020, 3, 21)])
    #messages = client.search(b'SINCE 20-Mar-2020')
    #messages = client.search([u'SINCE', datetime.datetime(2020, 3, 20)])
#messages = client.search([u'SINCE', datetime.datetime(2020, 3, 10),'FROM',redmine_sender],'utf8')
    messages = client.search([u'SINCE', datetime.datetime.now(),'FROM',redmine_sender],'utf8')
    # fetch selectors are passed as a simple list of strings.
    #response = client.fetch(messages, ['FLAGS', 'RFC822.SIZE'])
    for uid, message_data in client.fetch(messages, 'RFC822').items():
      print("uid=%d"%uid)
      email_message = email.message_from_bytes(message_data[b'RFC822'])
      #print(uid, email_message.get('From'), u"%s"%decode_header(email_message.get('Subject')))
      subj=decode_header(email_message.get('Subject'))
      message_id=decode_header(email_message.get('Message-ID'))
      date=decode_header(email_message.get('Date')[0][0])
      print("Date=%s"%date[0][0])
      date_dt=datetime.datetime.strptime('Sun, 29 Mar 2020 20:11:16 +1000', '%a, %d %b %Y %H:%M:%S %z')
      print("subj=%s"%subj[0][0].decode(subj[0][1]))
      print("Message-ID=%s"%message_id[0][0])

      # получаем телос сообщения:
      if email_message.is_multipart():
        for part in email_message.walk():
          ctype = part.get_content_type()
          cdispo = str(part.get('Content-Disposition'))

          # skip any text/plain (txt) attachments
          if ctype == 'text/plain' and 'attachment' not in cdispo:
            body = part.get_payload(decode=True)  # decode
            break
      # not multipart - i.e. plain text, no attachments, keeping fingers crossed
      else:
          body = email_message.get_payload(decode=True)

      d=body.decode('utf8')
      print("body=",d)
    return True





    date = (datetime.date.today() - datetime.timedelta(5)).strftime("%d-%b-%Y")
    #result, data = mail.uid('search', None, '(SENTSINCE {date} FROM "{redmine_sender}")'.format(date=date,redmine_sender=redmine_sender))
    result, data = mail.uid('search', None, '(FROM "{redmine_sender}")'.format(date=date,redmine_sender=redmine_sender))
    print("result=")
    print(result)
    print("data=")
    print(data)
    ids = str(data[0].decode('utf8')).replace("'","") # Получаем сроку номеров писем
    print("ids=",ids)
    id_list = ids.split() # Разделяем ID писем
    latest_email_id = id_list[-1] # Берем последний ID
    print("latest_email_id=",latest_email_id)
    result, data = mail.fetch(latest_email_id, "(RFC822)") # Получаем тело письма (RFC822) для данного ID
    raw_email = data[0][1] # Тело письма в необработанном виде
    # включает в себя заголовки и альтернативные полезные нагрузки)")")
    print(raw_email)
    return True
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    return None

def email_test(log,server,email,passwd):
  global client
  email_body="""Задача #120 была обновлена (Admin Redmine).


Первая вставка кода:
```        
  date = (datetime.date.today() - datetime.timedelta(5)).strftime("%d-%b-%Y")
  #result, data = mail.uid('search', None, '(SENTSINCE {date} FROM "{redmine_sender}")'.format(date=date,redmine_sender=redmine_sender))
  result, data = mail.uid('search', None, '(FROM "{redmine_sender}")'.format(date=date,redmine_sender=redmine_sender))
```
Вторая вставка кода:
```
    def email_test(log,server,email,passwd):
      global client
      message=""
      
      
      ""
      ret=init(log,server,email,passwd,maildir="INBOX")
      if ret == None:
        log.error("connect()")
        return False
      get_today_redmine_emails(log,client,redmine_sender="redmine@rsprim.ru")
```

----------------------------------------
Ошибка #120: Внедрить новый Redmine с канбаном
http://redmine.ru/issues/120#change-407

* Автор: Робот матрицы
* Статус: В работе
* Приоритет: Нормальный
* Назначена: Петров Пётр
* Категория: 
* Версия: 
----------------------------------------




-- 
Вы получили это уведомление, потому что вы либо подписаны на эту задачу, либо являетесь автором или исполнителем этой задачи.
Чтобы изменить настройки уведомлений, нажмите здесь: http://redmine.prim.drsk.ru/my/account"""
  message=email_message_to_matrix(log,email_body)
  print("message=",message)
  sys.exit()

  ret=init(log,server,email,passwd,maildir="INBOX")
  if ret == None:
    log.error("connect()")
    return False
  get_today_redmine_emails(log,client,redmine_sender="redmine@rsprim.ru")
  


if __name__ == '__main__':
  log=logging.getLogger("matrix_bot_logic_email")
  if conf.debug:
    log.setLevel(logging.DEBUG)
  else:
    log.setLevel(logging.INFO)

  # create the logging file handler
  fh = logging.FileHandler(conf.log_path_bot)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() %(levelname)s - %(message)s')
  fh.setFormatter(formatter)

  if conf.debug:
    # логирование в консоль:
    #stdout = logging.FileHandler("/dev/stdout")
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    log.addHandler(stdout)

  # add handler to logger object
  log.addHandler(fh)

  log.info("Program started")

  if len(sys.argv) < 4:
    log.error("need 3 param: email_server, email_address, email_passwd")
    sys.exit(1)

  if email_test(log,sys.argv[1],sys.argv[2],sys.argv[3]) == False:
    log.error("error redmine_test()")
    sys.exit(1)
  log.info("Program exit!")
