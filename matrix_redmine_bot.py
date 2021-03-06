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
from datetime import datetime
import threading
import traceback
import requests
import systemd_watchdog

from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from matrix_client.api import MatrixHttpLibError
from requests.exceptions import MissingSchema
import matrix_bot_api as mba
import matrix_bot_logic as mbl
import matrix_bot_logic_redmine as mblr
import matrix_bot_logic_email as mble
import config as conf
import copy

client = None
log = None
# Данные текущего состояния бота (настройки комнат), сохраняемые между запусками:
data={}
lock = None
wd = None
wd_timeout = 0
exit_flag=False

def get_exception_traceback_descr(e):
  if hasattr(e, '__traceback__'):
    tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
    result=""
    for msg in tb_str:
      result+=msg
    return result
  else:
    return e

def leave_room(room_id):
  global log
  global client
  global lock
  global data
  try:
    log.debug("=start function=")
    # Нужно выйти из комнаты:
    log.info("Leave from room: '%s'"%(room_id))
    response = client.api.leave_room(room_id)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("error leave room: '%s'"%(room_id))
    return False
  try:
    # И забыть её:
    log.info("Forgot room: '%s'"%(room_id))
    response = client.api.forget_room(room_id)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("error forgot room: '%s'"%(room_id))
    return False
  return True
    
def forgot_dialog(room_id):
  global log
  global client
  global lock
  global data
  try:
    log.debug("=start function=")
    log.debug("close_dialog()")
    log.debug("Try remove room: '%s' from data"%(room_id))
    if "rooms" in data:
      if room_id in data["rooms"]:
        # удаляем запись об этой комнате из данных:
        log.info("Remove room: '%s' from data"%room_id)
        del data["rooms"][room_id]
        log.info("save state data on disk")
        mbl.save_data(log,data)
        log.info("success forgot room '%s'"%(room_id))
        return True
      else:
        log.warning("unknown room '%s'"%room_id)
    else:
      log.error("empty data in data_file")

    log.info("do not forget room '%s'"%(room_id))
    return False
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("exception at execute forgot_dialog()")
    return False
    
# Called when a message is recieved.
def on_message(event):
    global client
    global log
    global lock
    log.debug("%s"%(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False)))
    if event['type'] == "m.room.member":
        if event['content']['membership'] == "join":
            log.info("{0} joined".format(event['content']['displayname']))
        # leave:
        elif event['content']['membership'] == "leave":
            log.info("{0} leave".format(event['sender']))
            # close room:
            log.debug("try lock() before access global data()")
            # проверяем, что мы остались одни:
            users = client.rooms[event['room_id']].get_joined_members()
            if users == None:
              log.error("room.get_joined_members()")
              return False
            users_num = len(users)
            log.debug("users_num=%d"%users_num)
            if users_num==1:
              # мы остались одни - выходим из комнаты:
              if leave_room(event['room_id']) == False:
                log.error("leave_room()")
                return False
              with lock:
                log.debug("success lock before process_command()")
                if forgot_dialog(event['room_id']) == False:
                  log.warning("forgot_dialog()==False")
              log.debug("release lock() after access global data")
        return True
    elif event['type'] == "m.room.message":
        if event['content']['msgtype'] == "m.text":
            reply_to_id=None
            if "m.relates_to" in  event['content'] and "m.in_reply_to" in event['content']["m.relates_to"]:
              # это ответ на сообщение:
              try:
                if 'm.in_reply_to' in event['content']['m.relates_to']:
                  reply_to_id=event['content']['m.relates_to']['m.in_reply_to']['event_id']
                else:
                  reply_to_id=event['content']['m.relates_to']['event_id']
              except:
                log.error("bad formated event reply - skip")
                #mba.send_message(log,client,event['room_id'],"Внутренняя ошибка разбора сообщения - обратитесь к разработчику")
                log.debug(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))
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
        elif event['content']['msgtype'] == "m.image" or \
          event['content']['msgtype'] == "m.file":
          try:
            if "file" in event['content'] and \
              "v" in event['content']["file"] and\
              event['content']["file"]["v"]=="v2":

              file_type=event['content']['info']['mimetype']
              file_url=event['content']['file']['url']
            else:
              file_type=event['content']['info']['mimetype']
              file_url=event['content']['url']
          except Exception as e:
            log.error("bad formated event reply - skip")
            log.error(get_exception_traceback_descr(e))
            #mba.send_message(log,client,event['room_id'],"Внутренняя ошибка разбора сообщения - обратитесь к разработчику")
            log.debug(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))
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
    if event_item['type'] == "m.room.member":
      if event_item['content']['membership'] == "invite":
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
          room_class.send_text("Спасибо за приглашение! Недеюсь быть Вам полезным. Для справки наберите: мой_ник help")
          room_class.send_text("Для справки по доступным командам - неберите: 'my_nick help'")
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
            mbl.save_data(log,data)
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
    return client

def exception_handler(e):
  global log
  global wd
  global exit_flag
  log.error("exception_handler(): main listener thread except. He must retrying...")
  log.error(e)
  if conf.use_watchdog:
    log.info("send to watchdog error service status")
    wd.notify_error("An irrecoverable error occured! exception_handler()")
  log.info("exception_handler(): wait 5 second before programm exit...")
  exit_flag=True
  time.sleep(5)
  log.info("sys.exit(1)")
  sys.exit(1)

def main():
  global client
  global data
  global log
  global lock
  global wd
  global wd_timeout
  global exit_flag

  con=None
  cur=None

  # watchdog:
  if conf.use_watchdog:
    log.info("init watchdog")
    wd = systemd_watchdog.watchdog()
    if not wd.is_enabled:
      # Then it's probably not running is systemd with watchdog enabled
      log.error("Watchdog not enabled in systemdunit, but enabled in bot config!")
      return False
    wd.status("Starting my service...")
    wd_timeout=int(float(wd.timeout) / 1000000)
    log.info("watchdog timeout=%d"%wd_timeout)

  lock = threading.RLock()

  log.debug("try lock() before access global data()")
  with lock:
    log.debug("success lock() before access global data")
    data=mbl.load_data(log)
  log.debug("release lock() after access global data")

  if mbl.init(log,conf.matrix_bot_logic_file,data)==False:
    log.error("error matrix_bot_logic.init()")
    sys.exit(1)
  if mblr.init(log,conf.redmine_server,conf.redmine_api_access_key) == False:
    log.error("error matrix_bot_logic_redmine.init()")
    sys.exit(1)

  log.info("try init matrix-client")
  client = matrix_connect()
  log.info("success init matrix-client")
  if client == None:
    log.error("matrix_connect()")
    return False

  try:
    log.info("try init listeners")
    client.add_listener(on_message)
    client.add_invite_listener(on_invite)
    client.start_listener_thread(exception_handler=exception_handler)
    log.info("success init listeners")
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("exception at execute main() at init listeners")
    sys.exit(1)
  
  # программа инициализировалась - сообщаем об этом в watchdog:
  if conf.use_watchdog:
    wd.ready()
    wd.status("start main loop")
    log.debug("watchdog send notify")
    wd.notify()

  try:
    while exit_flag == False:
      ##################
      # watchdog notify:
      if conf.use_watchdog:
        wd.notify()

      #log.debug("new step")
      # отправляем уведомления с почты, если таковые имеются:
      data_copy=None
      with lock:
        log.debug("success lock() before access global data")
        # get deep copy:
        # https://stackoverflow.com/questions/2465921/how-to-copy-a-dictionary-and-only-edit-the-copy
        log.debug("do deep copy of global data fro mail proccess")
        data_copy=copy.deepcopy(data)
        log.debug("success do deep copy of global data fro mail proccess")
      log.debug("release lock() after access global data")

      for room in data_copy["rooms"]:
        # watchdog notify:
        if conf.use_watchdog:
          log.debug("watchdog send notify")
          wd.notify()
        room_data=data_copy["rooms"][room]
        if "redmine_notify_email" in room_data and \
          "redmine_notify_email_passwd" in room_data and \
          "redmine_notify_email_server" in room_data:

          redmine_notify_email=room_data["redmine_notify_email"]
          redmine_notify_email_passwd=room_data["redmine_notify_email_passwd"]
          redmine_notify_email_server=room_data["redmine_notify_email_server"]
          last_email_timestamp=0
          last_email_message_ids=[]

          if "last_email_timestamp" in room_data:
            last_email_timestamp=room_data["last_email_timestamp"]
          if "last_email_message_ids" in room_data:
            last_email_message_ids=room_data["last_email_message_ids"]

          log.info("==========  proccess notify for room=%s, email=%s, last_email_timestamp=%d (%s) =========="%(room,redmine_notify_email,last_email_timestamp,\
            datetime.fromtimestamp(last_email_timestamp).strftime('%Y-%m-%d %H:%M:%S')))
          # выводим все идентификаторы последних писем за последний timestamp:
          log.debug("last_email_message_ids=")
          log.debug(last_email_message_ids)
          for item in last_email_message_ids:
            log.debug("last_email_message_id=%s"%item)
            
          ret=mble.send_new_notify(log,client,room,last_email_timestamp, last_email_message_ids, redmine_notify_email_server, redmine_notify_email, redmine_notify_email_passwd, mailbox="inbox", redmine_sender=conf.redmine_email_return_address)
          if ret == None:
            log.error("mble.send_new_notify()")
            # продолжаем для других комнат
          else:
            log.debug("last_email_message_ids=")
            log.debug(last_email_message_ids)
            log.debug("mble.send_new_notify() ret=")
            log.debug(ret)
            log.debug("mble.send_new_notify() ret['last_email_message_ids']=")
            log.debug(ret["last_email_message_ids"])
            if last_email_timestamp != ret["last_email_timestamp"] or last_email_message_ids != ret["last_email_message_ids"] or "last_email_message_ids" not in room_data:
              log.debug("previouse: last_email_timestamp=%d (%s)"%(last_email_timestamp,\
                datetime.fromtimestamp(last_email_timestamp).strftime('%Y-%m-%d %H:%M:%S')))
              for item in last_email_message_ids:
                log.debug("previouse last_email_message_id=%s"%item)

              log.debug("new: last_email_timestamp=%d (%s)"%(ret["last_email_timestamp"],\
                datetime.fromtimestamp(ret["last_email_timestamp"]).strftime('%Y-%m-%d %H:%M:%S')))
              for item in ret["last_email_message_ids"]:
                log.debug("new last_email_message_id=%s"%item)
              with lock:
                log.debug("success lock() before access global data")
                if room in data["rooms"]:
                  data["rooms"][room]["last_email_timestamp"]=ret["last_email_timestamp"]
                  data["rooms"][room]["last_email_message_ids"]=ret["last_email_message_ids"]
                  mbl.save_data(log,data)
                  log.debug("succss save new last_email_timestamp and last_email_message_ids")
                else:
                  log.debug("room '%s' was removed from data when processed - skip"%room)
              log.debug("success unlock() after access global data")
            else:
              log.debug("no new email messages - skip for this room")

      # watchdog notify:
      if conf.use_watchdog:
        log.debug("watchdog send notify")
        wd.notify()
      log.debug("step")
      time.sleep(30)
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("exception at execute main() at proccess emails")
    sys.exit(1)
  if exit_flag == True:
    log.error("catch exit_flag==True - error occur - return False")
    return False
  return True

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

  if main()==False:
    log.error("error main()")
    sys.exit(1)
  log.info("Program success exit")
