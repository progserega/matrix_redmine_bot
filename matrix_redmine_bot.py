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
from logging import handlers
import time
import json
import os
import pickle
import re
import threading
#import MySQLdb as mdb
import traceback
import requests

from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from matrix_client.api import MatrixHttpLibError
from requests.exceptions import MissingSchema
import sendemail as mail
import matrix_bot_api as mba
import matrix_bot_logic as mbl
import config as conf

client = None
log = None
data={}
lock = None

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

# Called when a message is recieved.
def on_message(event):
    global client
    global log
    global lock
    log.debug("%s"%(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False)))
    if event['type'] == "m.room.member":
        if event['content']['membership'] == "join":
            log.info("{0} joined".format(event['content']['displayname']))
    elif event['type'] == "m.room.message":
        if event['content']['msgtype'] == "m.text":
            reply_to_id=None
            if "m.relates_to" in  event['content']:
              # это ответ на сообщение:
              try:
                reply_to_id=event['content']['m.relates_to']['m.in_reply_to']['event_id']
              except:
                log.error("bad formated event reply - skip")
                mba.send_message(log,client,event['room_id'],"Внутренняя ошибка разбора сообщения - обратитесь к разработчику")
                return False
            formatted_body=None
            format_type=None
            if "formatted_body" in event['content'] and "format" in event['content']:
              formatted_body=event['content']['formatted_body']
              format_type=event['content']['format']
            log.debug("{0}: {1}".format(event['sender'], event['content']['body']))
            log.debug("try lock before mbl.process_message()")
            with lock:
              log.debug("success lock before mbl.process_message()")
              if mbl.process_message(\
                  log,client,event['sender'],\
                  event['room_id'],\
                  event['content']['body'],\
                  formated_message=formatted_body,\
                  format_type=format_type,\
                  reply_to_id=reply_to_id,\
                  file_url=None,\
                  file_type=None\
                ) == False:
                log.error("error process command: '%s'"%event['content']['body'])
                mba.send_message(log,client,event['room_id'],"Внутренняя бота - обратитесь к разработчику")
                return False
        elif event['content']['msgtype'] == "m.image":
          try:
            file_type=event['content']['info']['mimetype']
            file_url=event['content']['url']
          except:
            log.error("bad formated event reply - skip")
            mba.send_message(log,client,event['room_id'],"Внутренняя ошибка разбора сообщения - обратитесь к разработчику")
            return False
          log.debug("{0}: {1}".format(event['sender'], event['content']['body']))
          log.debug("try lock before mbl.process_message()")
          with lock:
            log.debug("success lock before mbl.process_message()")
            if mbl.process_message(\
                log,client,event['sender'],\
                event['room_id'],\
                event['content']['body'],\
                formated_message=None,\
                format_type=None,\
                reply_to_id=None,\
                file_url=file_url,\
                file_type=file_type\
              ) == False:
              log.error("error process command: '%s'"%event['content']['body'])
              return False

    else:
      log.debug(event['type'])
    return True

def on_invite(room, event):
  global client
  global log
  global lock
  global data
  log.debug("=start function=")

  log.debug(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))

  # Просматриваем сообщения:
  for event_item in event['events']:
    if event_item['type'] == "m.room.join_rules":
      if event_item['content']['join_rule'] == "invite":
        user=event_item["sender"]
        # проверка на разрешения:
        allow=False
        if len(conf.allow_domains)>0:
          for allow_domain in conf.allow_domains:
            if re.search('.*:%s$'%allow_domain.lower(), user.lower()) is not None:
              allow=True
              log.info("user: %s from allow domain: %s - allow invite"%(user, allow_domain))
              break
        if len(conf.allow_users)>0:
          for allow_user in conf.allow_users:
            if allow_user.lower() == user.lower():
              allow=True
              log.info("user: %s from allow users - allow invite"%user)
              break
        if len(conf.allow_domains)==0 and  len(conf.allow_users)==0:
          allow=True

        if allow == True:
          # Приглашение вступить в комнату:
          log.debug("try join to room: %s"%room)
          log.info("wait 3 second before join for bug https://github.com/matrix-org/synapse/issues/2367...")
          time.sleep(3)
          room_class = client.join_room(room)
          log.debug("success join to room: %s"%room)
          room_class.send_text("Спасибо за приглашение! Недеюсь быть Вам полезным. :-)")
          room_class.send_text("Для справки по доступным командам - неберите: '%s help'"%conf.bot_command)
          log.debug("success send 'hello' to room: %s"%room)
          log.info("User '%s' invite me to room: %s and I success join to room"%(user,room))
          # Прописываем системную группу для пользователя 
          # (группа, в которую будут сыпаться системные сообщения от бота и где он будет слушать команды):
          with lock:
            if "rooms" not in data:
              data["rooms"]={}
            if room not in data["rooms"]:
              data["rooms"][room]={}
              data["rooms"][room]["invite_user"]=user
            mbl.save_data(data)
          log.debug("release lock() after access global data")
        else:
          log.warning("not allowed invite from user: %s - ignore invite"%user)

def matrix_connect():
    global log
    global lock

    client = MatrixClient(conf.matrix_server)
    try:
        token = client.login(username=conf.matrix_username, password=conf.matrix_password,device_id=conf.matrix_device_id)
    except MatrixRequestError as e:
        log.error(e)
        log.debug(e)
        if e.code == 403:
            log.error("Bad username or password.")
            return None
        else:
            log.error("Check your sever details are correct.")
            return None
    except MatrixHttpLibError as e:
        log.error(e)
        return None
    except MissingSchema as e:
        log.error("Bad URL format.")
        log.error(e)
        log.debug(e)
        return None
    except:
        log.error("unknown error at client.login()")
        return None
    return client

def exception_handler(e):
  global log
  log.error("exception_handler(): main listener thread except. He must retrying...")
  log.error(e)
  log.info("exception_handler(): wait 5 second before retrying...")
  time.sleep(5)

def main():
    global client
    global data
    global log
    global lock

    con=None
    cur=None

    lock = threading.RLock()

    client.add_listener(on_message)
    client.add_invite_listener(on_invite)

    client.start_listener_thread(exception_handler=exception_handler)

    while True:
      ##################
      #log.debug("new step")
      time.sleep(30)

if __name__ == '__main__':
  log=logging.getLogger("matrix_redmine_bot")
  log_lib=logging.getLogger("matrix_client.client")
  if conf.debug:
    log.setLevel(logging.DEBUG)
  else:
    log.setLevel(logging.INFO)

  # create the logging file handler
#fh = logging.FileHandler(conf.log_path)
  fh = logging.handlers.TimedRotatingFileHandler(conf.log_path_bot, when=conf.log_backup_when, backupCount=conf.log_backup_count)
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s() %(levelname)s - %(message)s')
  fh.setFormatter(formatter)

  if conf.debug:
    # логирование в консоль:
    #stdout = logging.FileHandler("/dev/stdout")
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    log.addHandler(stdout)
    log_lib.addHandler(stdout)

  # add handler to logger object
  log.addHandler(fh)
  log_lib.addHandler(fh)

  log.info("Program started")
  if mbl.init(log,conf.matrix_bot_logic_file)==False:
    log.error("error matrix_bot_logic.init()")
    sys.exit(1)
  if mblr.init(log,conf.redmine_server,conf.redmine_api_access_key) == False:
    log.error("error matrix_bot_logic_redmine.init()")
    sys.exit(1)

  if main()==False:
    log.error("error main()")
    sys.exit(1)
  log.info("Program exit!")
