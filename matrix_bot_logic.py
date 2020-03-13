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
import json
import os
import traceback
import re
import requests
import matrix_bot_api as mba
import matrix_bot_logic_redmine as mblr
import config as conf
from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from matrix_client.api import MatrixHttpLibError
from requests.exceptions import MissingSchema

client = None
log = None
logic={}
lock = None
memmory = {}

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

def is_room_public(log,room):
  global client
  # Проверяем сколько в комнате пользователей. Если более двух - то это не приватный чат и потому не отвечаем на команды:
  users = client.rooms[room].get_joined_members()
  if users == None:
    log.error("room.get_joined_members()")
    return False
  users_num = len(users)
  log.debug("in room %d users"%users_num)
  if users_num > 2:
    # публичная комната - не обрабатываем команды:
    log.debug("this is public room - skip proccess_commands")
    return True
  else:
    log.debug("this is private chat (2 users) - proccess commands")
    return False

def process_message(log,client,user,room,message,formated_message=None,format_type=None,reply_to_id=None,file_url=None,file_type=None):
  global logic
  global memmory
  source_message=None
  source_cmd=None

  if reply_to_id!=None and format_type=="org.matrix.custom.html" and formated_message!=None:
    # разбираем, чтобы получить исходное сообщение и ответ
    source_message=re.sub('<mx-reply><blockquote>.*<\/a><br>','', formated_message)
    source_message=re.sub('</blockquote></mx-reply>.*','', source_message)
    source_cmd=re.sub(r'.*</blockquote></mx-reply>','', formated_message.replace('\n',''))
    log.debug("source=%s"%source_message)
    log.debug("cmd=%s"%source_cmd)
    message=source_cmd

  if is_room_public(log,room):
    if re.match('^%s'%conf.bot_command, message) != None:
      # убираем командный префикс:
      message=re.sub('^%s '%conf.bot_command,'', message)
    else:
      # пользователь обращается НЕ к роботу - пропуск обработки
      log.debug("skip message in public room without our name")
      return True

  # обработка по логике
  log.debug("get cmd: %s"%message)
  log.debug("user=%s"%user)
  if user == conf.matrix_username or "@%s:"%conf.matrix_username in user:
    log.debug("message from us - skip")
    return True
  state=get_state(log,room)
  if state==None:
    log.error("get_state(log,%s)"%room)
    return False

  for cmd in state:
    if message.lower() == u"отмена" or message.lower() == "cancel" or message.lower() == "0":
      # Стандартная команда отмены - перехода в начальное меню:
      set_state(room,logic)
      text="Переход в начало меню. Наберите 'помощь' или 'help' для спрвки по командам"
      if mba.send_message(log,client,room,text) == False:
        log.error("send_message() to room")
        log.error("cur state:")
        log.error(state)
        return False
      return True

    if check_equal_cmd(state,message.lower(),cmd) or cmd == "*":
      data=state[cmd]
      # Шлём стандартное для этого состояния сообщение:
      if "message" in data:
        # поддержка переменных в сообщениях:
        text=replace_env2val(log,room,data["message"])
        if text==None:
          text=data["message"]
        if "message_type" in data and data["message_type"]=="html":
          if mba.send_html(log,client,room,text) == False:
            log.error("send_html() to room %s"%room)
            log.error("cur state:")
            log.error(state)
            return False
        else:
          if mba.send_message(log,client,room,text) == False:
            log.error("send_message() to room")
            log.error("cur state:")
            log.error(state)
            return False
      # Устанавливаем переданный пользователем текст, как переменную (если так описано в правиле логики бота):
      if "set_env" in data:
        set_env(room,data["set_env"],message)
      # Устанавливаем статическую переменную (значение может содержать переменную в {}):
      if "set_static_keys" in data:
        for key in data["set_static_keys"]:
          val=data["set_static_keys"][key]
          # в цикле заменяем значения переменной
          val=replace_env2val(log,room,val)
          if val == None:
            log.error("replace_env2val()")
            bot_fault(log,client,room)
            log.error("cur state:")
            log.error(state)
            return False
          set_env(room,key,val)
      # Проверяем, что должны сделать:
      # Отмена:
      if data["type"]=="sys_cmd_cancel":
        set_state(room,logic)
        return True
      # Обычная команда:
      if data["type"]=="cmd":
        set_state(room,data["answer"])
        return True

      #=========================== redmine =====================================
      if data["type"]=="redmine_check_login":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)
        redmine_user_name=get_env(room,"redmine_login")
        if redmine_user_name == None:
          log.error("get_env('redmine_login')")
          if mba.send_message(log,client,room,"Внутренняя ошибка бота") == False:
            log.error("send_message() to user")
            return False
        redmine_user_id=mblr.get_user_id_by_name(log,redmine_user_name)
        if redmine_user_id == None:
          if mba.send_message(log,client,room,"Некорректный redmine_login - попробуйте ещё раз") == False:
            log.error("send_message() to user")
            return False
          return True
        else:
          set_state(room,logic)
          set_env(room,"redmine_user_id",redmine_user_id)
          if mblr.redmine_update_hosts_groups_of_user(log,user) == False:
            log.error('error save groups of room')
            if mba.send_message(log,client,room,"error save groups of room") == False:
              log.error("send_message() to room")
              return False
          if mba.send_message(log,client,room,"сохранил redmine_login '%s' для вас. Теперь вы будет получать статистику из групп, в которые входит этот пользователь\nВернулся в основное меню"%redmine_login) == False:
            log.error("send_message() to room")
            return False
          return True
          
      if data["type"]=="redmine_new_issue":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)
        return mblr.redmine_new_issue(log,logic,client,room,user,data,message,cmd)
      if data["type"]=="redmine_show_stat":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)
        return mblr.redmine_show_stat(log,logic,client,room,user,data,message,cmd)
      #=========================== redmine  - конец =====================================

  if get_state(log,room) == logic:
    # Пользователь пишет что попало в самом начале диалога:
    return True
  else:
    if mba.send_message(log,client,room,"Не распознал команду - похоже я её не знаю... Пожалуйста, введите варианты описанные выше или 'отмена' или '0'") == False:
      log.error("send_message() to room")
      return False
  return True

def replace_env2val(log,room,val):
  all_env=get_env_list(room)
  if all_env == None:
    # Нет переменных, возвращаем неизменную строку:
    return val
  for env_name in all_env:
    env_val=get_env(room,env_name)
    if env_val == None:
      return None
    if type(env_val) == str: # or type(env_val) == unicode:
      val=val.replace("{%s}"%env_name,env_val,100)
    elif type(env_val) == float:
      val=val.replace("{%s}"%env_name,"%f"%env_val,100)
    elif type(env_val) == int:
      val=val.replace("{%s}"%env_name,"%d"%env_val,100)
    else:
      log.warning("unsupported type of env. env_name=%s, type=%s"%(env_name,type(env_val)))
  return val


def bot_fault(log,client,room):
  if mba.send_message(log,client,room,"Внутренняя ошибка бота - пожалуйста, обратитесь в отдел ИТ") == False:
    log.error("send_message() to user")
    log.error("cur state:")
    log.error(state)
    return False
  return True

def go_to_main_menu(log,logic,client,room,user):
  log.debug("go_to_main_menu()")
  log.info("return to main menu in logic")
  if mba.send_notice(log,client,room,u"возвращаюсь в начальное меню. Отправьте 'помощь' или '1' для получения справки.") == False:
    log.error("send_notice() to user %s"%user)
  reset_room_memmory(room)
  set_state(room,logic)
  return True

def check_equal_cmd(state,message,key):
  global logic
  if message == key:
    return True
  if "aliases" in state[key]:
    for alias in state[key]["aliases"]:
      if message == alias:
        return True
  return False

def get_env(room,env_name):
  global memmory
  if "rooms" not in memmory:
    return None
  if room not in memmory["rooms"]:
    return None
  if "env" not in memmory["rooms"][room]:
    return None
  if env_name not in memmory["rooms"][room]["env"]:
    return None
  return memmory["rooms"][room]["env"][env_name]

def get_env_list(room):
  global memmory
  if "rooms" not in memmory:
    return None
  if room not in memmory["rooms"]:
    return None
  if "env" not in memmory["rooms"][room]:
    return None
  return memmory["rooms"][room]["env"]

def set_env(room,env_name,env_val):
  global memmory
  if "rooms" not in memmory:
    return None
  if room not in memmory["rooms"]:
    memmory["rooms"][room]={}
  if "env" not in memmory["rooms"][room]:
    memmory["rooms"][room]["env"]={}
  memmory["rooms"][room]["env"][env_name]=env_val
  return True

def set_state(room,state):
  global memmory
  global logic
  if "rooms" not in memmory:
    return None
  if room not in memmory["rooms"]:
    memmory["rooms"][room]={}
  memmory["rooms"][room]["state"]=state
  return True

def reset_room_memmory(room):
  global memmory
  if "rooms" not in memmory:
    return None
  if room in memmory["rooms"]:
    del memmory["rooms"][room]
  return True

def get_state(log,room):
  global memmory
  global logic
  if "rooms" not in memmory:
    return None
  if room in memmory["rooms"]:
    if "state" not in memmory["rooms"][room]:
      log.error("memmory corrupt for room %s - can not find 'state' struct"%room)
      return None
    else:
      return memmory["rooms"][room]["state"]
  else:
    # Иначе возвращаем начальный статус логики:
    return logic

def init(log,rule_file):
  global logic
  try:
    json_data=open(rule_file,"r",encoding="utf-8").read()
  except Exception as e:
    log.error("open file")
    log.error(get_exception_traceback_descr(e))
    return None
  try:
    logic = json.loads(json_data)
  except Exception as e:
    log.error("parse logic rule file: %s"%e)
    log.error(get_exception_traceback_descr(e))
    return False
  return True

def save_data(data):
  global log
  log.debug("=start function=")
  log.debug("save to data_file:%s"%conf.data_file)
  try:
    #data_file=open(conf.data_file,"wb")
    data_file=open(conf.data_file,"w")
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("open(%s) for writing"%conf.data_file)
    return False
    
  try:
    data_file.write(json.dumps(data, indent=4, sort_keys=True,ensure_ascii=False))
    #pickle.dump(data,data_file)
    data_file.close()
  except Exception as e:
    log.error(get_exception_traceback_descr(e))
    log.error("json.dump to '%s'"%conf.data_file)
    print(json.dumps(data, indent=4, sort_keys=True,ensure_ascii=False))
    sys.exit(1)
    return False
  return True

def load_data():
  global log
  log.debug("=start function=")
  tmp_data_file=conf.data_file
  reset=False
  if os.path.exists(tmp_data_file):
    log.debug("Загружаем файл промежуточных данных: '%s'" % tmp_data_file)
    #data_file = open(tmp_data_file,'rb')
    data_file = open(tmp_data_file,'r')
    try:
      #data=pickle.load(data_file)
      data=json.loads(data_file.read())
      data_file.close()
      log.debug("Загрузили файл промежуточных данных: '%s'" % tmp_data_file)
      if not "rooms" in data:
        log.warning("Битый файл сессии - сброс")
        reset=True
      else:
        # успешно загрузили файл состояния - он в хорошем состоянии - сохраняем его как бэкап:
        try:
          backup_name=conf.data_file+'.backup'
          log.info("сохраняем успешно-загруженный файл как '%s'"%backup_name)
          f=open(backup_name,"w+")
          f.write(json.dumps(data, indent=4, sort_keys=True,ensure_ascii=False))
          f.close()
        except Exception as e:
          log.error(get_exception_traceback_descr(e))
          log.error("json.dump to '%s'"%conf.data_file)
          print(json.dumps(data, indent=4, sort_keys=True,ensure_ascii=False))
          sys.exit(1)
            
    except Exception as e:
      log.error(get_exception_traceback_descr(e))
      log.warning("Битый файл сессии - сброс")
      reset=True
  else:
    log.warning("Файл промежуточных данных не существует")
    reset=True
  if reset:
    try:
      log.info("сохраняем копию битого файла основных данных")
      backup_name=conf.data_file+'.failed.'+uuid.uuid4().hex
      log.warning("сохраняем битый файл как '%s'"%backup_name)
      f=open(conf.data_file,"r")
      backup_data=f.read()
      f.close()
      f=open(backup_name,"w+")
      f.write(backup_data)
      f.close()
      log.info("сохраняем бэкап последнего успешно-загруженного файла, чтобы его не перетёрло в случае сброса файла")
      backup_name=conf.data_file+'.backup'
      new_backup_name=conf.data_file+'.backup.'+uuid.uuid4().hex
      log.info("сохраняем прошлый бэкап файла данны как '%s'"%new_backup_name)
      f=open(backup_name,"r")
      backup_data=f.read()
      f.close()
      f=open(new_backup_name,"w+")
      f.write(backup_data)
      f.close()
    except Exception as e:
      log.error(get_exception_traceback_descr(e))
      log.warning("ошибка копирования битого файла данных в резервную копию или копирования прошлого бэкапа")
    if conf.try_recover_data_file_from_last_backup == True:
      log.info("пробуем загрузить последний успешный бэкап")
      try:
        backup_name=conf.data_file+'.backup'
        data_file = open(backup_name,'r')
        data=json.loads(data_file.read())
        data_file.close()
        if not "rooms" in data:
          log.warning("Битый файл сессии и в файле бэкапа :-( - сброс")
          reset=True
        else:
          log.debug("Загрузили файл промежуточных данных из последнего бэкапа: '%s'" % backup_name)
          reset=False
      except Exception as e:
        log.error(get_exception_traceback_descr(e))
        log.warning("Битый файл сессии и в файле бэкапа или бэкапа не существует :-( - сброс")
        reset=True
    if reset:
      log.warning("Сброс промежуточных данных")
      data={}
      data["rooms"]={}
    save_data(data)
  #debug_dump_json_to_file("debug_data_as_json.json",data)
  return data
