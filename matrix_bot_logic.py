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
import uuid
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

log = None
logic={}
lock = None

# состояние стэйт-машины, не сохраняемые между запусками:
memmory = {}
data_file= {}

def process_message(log,client_class,user,room,message,formated_message=None,format_type=None,reply_to_id=None,file_url=None,file_type=None):
  global logic
  global memmory
  source_message=None
  source_cmd=None
  client=client_class

  # инициализация данных, если для данной комнаты они пусты:
  if "rooms" not in data_file:
    data_file["rooms"]={}
  if room not in data_file["rooms"]:
    data_file["rooms"][room]={}

  if reply_to_id!=None and format_type=="org.matrix.custom.html" and formated_message!=None:
    # разбираем, чтобы получить исходное сообщение и ответ
    source_message=re.sub('<mx-reply><blockquote>.*<\/a><br>','', formated_message)
    source_message=re.sub('</blockquote></mx-reply>.*','', source_message)
    source_cmd=re.sub(r'.*</blockquote></mx-reply>','', formated_message.replace('\n',''))
    # выкусываем обёртку над ником:
    source_cmd=re.sub(r'^<a href="https://matrix.to/#/@[A-Za-z:\.]*">','',source_cmd)
    source_cmd=re.sub(r'</a>','',source_cmd)

    log.debug("source=%s"%source_message)
    log.debug("cmd=%s"%source_cmd)
    message=source_cmd.strip()

  # имя бота:
  nick_name=client.api.get_display_name(client.user_id)
  log.debug("nick_name=%s"%nick_name)

  if re.match(r'^!*%s:* '%nick_name.lower(), message.lower()) != None:
    # убираем командный префикс:
    #message=re.sub('^!*%s:* '%nick_name.lower(),'', message)
    log.debug("remove prefix from cmd")
    # разделяем только один раз (первое слово), а потом берём "второе слово",
    # которое содержит всю оставшуюся строку:
    message=message.split(' ',1)[1]
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
    log.warning("get_state(log,%s)"%room)
    set_state(room,logic)
    state=get_state(log,room)
    if state==None:
      log.error("get_state(log,%s)"%room)
      return False

  # получаем уровень прав пользователя:
  users_power_levels=client.api.get_power_levels(room)
  # управление ботом для пользователей с уровнем выше или равно "модератор":
  power_min_level=users_power_levels["ban"]
  user_can_moderate=False
  if users_power_levels["users"][user] >= power_min_level:
    user_can_moderate=True
    log.debug("user can moderate")

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

    cmd_words=message.split(' ')
    if len(cmd_words)> 0 and check_equal_cmd(state,cmd_words[0].lower(),cmd) or cmd == "*":
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
      # команда проверки и сохранения логина:
      if data["type"]=="redmine_check_login":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)

        # проверка прав пользователя:
        if user_can_moderate==False:
          if mba.send_message(log,client,room,"Только пользователь с правами больше или равно, чем 'модератор' может управлять настройками бота.") == False:
            log.error("send_message() to user")
            return False
          set_state(room,logic)
          return True
          
        redmine_user_name=get_env(room,"redmine_login")
        if redmine_user_name == None:
          log.error("get_env('redmine_login')")
          if mba.send_message(log,client,room,"Внутренняя ошибка бота") == False:
            log.error("send_message() to user")
            return False
          return False
        redmine_user_id=mblr.get_user_id_by_name(log,redmine_user_name)
        if redmine_user_id == -3:
          if mba.send_message(log,client,room,"Неуникальное имя - redmine сообщает, что есть нескольколько пользователей с таким логином - попробуйте ещё раз") == False:
            log.error("send_message() to user")
            return False
          return True
        elif redmine_user_id == -2:
          if mba.send_message(log,client,room,"Некорректный redmine_login - попробуйте ещё раз") == False:
            log.error("send_message() to user")
            return False
          return True
        elif redmine_user_id == -1:
          if mba.send_message(log,client,room,"Внутренняя ошибка бота") == False:
            log.error("send_message() to user")
            return False
          return False
        else:
          set_state(room,logic)
          # запоминаем настройки в данных робота:
          data_file["rooms"][room]["redmine_user_id"]=redmine_user_id
          data_file["rooms"][room]["redmine_user_name"]=redmine_user_name
          save_data(log,data_file)
          if mba.send_message(log,client,room,"Сохранил redmine_login для этой комнаты. Теперь вы будете \
получать задачи и уведомления (если захотите) для пользователя redmine %s (url=%s/users/%d).\nВернулся в основное меню"%\
(redmine_user_name,conf.redmine_server,redmine_user_id)) == False:
            log.error("send_message() to room")
            return False
          return True

      # команда установки настройки проекта по-умолчанию:
      if data["type"]=="redmine_set_def_project":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)

        # проверка прав пользователя:
        if user_can_moderate==False:
          if mba.send_message(log,client,room,"Только пользователь с правами больше или равно, чем 'модератор' может управлять настройками бота.") == False:
            log.error("send_message() to user")
            return False
          set_state(room,logic)
          return True
          
        redmine_project_ids=get_env(room,"redmine_project")
        if redmine_project_ids == None:
          log.error("get_env('redmine_project')")
          if mba.send_message(log,client,room,"Внутренняя ошибка бота") == False:
            log.error("send_message() to user")
            return False
          return False

        redmine_project_id_list=redmine_project_ids.split(',')


        for redmine_project_id in redmine_project_id_list:
          # проверяем все идентификаторы на корректность:
          ret=mblr.check_project_exist(log,redmine_project_id)
          if ret == False:
            if mba.send_message(log,client,room,"Некорректный идентификатор проекта '%s' - попробуйте ещё раз"%redmine_project_id) == False:
              log.error("send_message() to user")
              return False
            return True
          elif ret == None:
            if mba.send_message(log,client,room,"Внутренняя ошибка бота") == False:
              log.error("send_message() to user")
              return False
            return False

          # все првоерили и не вывалились из функции - значит все корректны:
          set_state(room,logic)
          # запоминаем настройки в данных робота:
          data_file["rooms"][room]["redmine_def_project_id"]=redmine_project_id_list
          save_data(log,data_file)

          text_message="Сохранил идентификатор(ы) проекта для этой комнаты. Задачи из этой комнаты будут создаваться в проекте:\n"
          for redmine_project_id in redmine_project_id_list:
            text_message+="%s/projects/%s\n"%(conf.redmine_server,redmine_project_id)
          text_message+="Вернулся в основное меню"
          if mba.send_message(log,client,room,text_message) == False:
            log.error("send_message() to room")
            return False
          return True

      # настройки комнаты:
      if data["type"]=="redmine_show_room_config":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)
        text="Настройки для комнаты:\n<pre><code>"
        text+=json.dumps(data_file["rooms"][room], indent=4, sort_keys=True,ensure_ascii=False)
        text+="\n</code></pre>\n"
        set_state(room,logic)
        if mba.send_html(log,client,room,text) == False:
          log.error("send_message() to room")
          return False
        return True
          
      if data["type"]=="redmine_new_issue":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)

        log.debug("len=%d"%len(message))
        # разбор строки:
        if len(cmd_words)==1:
          text="""Необходимо добавить тему и, возможно, описание ошибки. Например:
  %(redmine_nick)s bug тема ошибки
или:
  %(redmine_nick)s bug "тема ошибки" "детальное описание ошибки"

При этом алиасом для "bug" может быть: "ошибка", "issue" или 3
"""%{"redmine_nick":nick_name}

          if mba.send_message(log,client,room,text) == False:
            log.error("send_message() to user")
            return False
          return True

        # базовые настройки для параметров ошибки:
        if "redmine_def_project_id" in data_file["rooms"][room]:
          project_id=data_file["rooms"][room]["redmine_def_project_id"]
        else:
          project_id=conf.redmine_def_project_id
        descr=""
        subj=""
        params=""
        for w in cmd_words[1:]:
          params+=w
          params+=" "

        log.debug("params=%s"%params)
        
        if '"' not in params:
          # нет кавычек - значит весь текст - тема ошибки:
          subj=params
        else:
          param_list=params.split('"')
          log.debug(param_list)
          clear_param_list=[]
          for p in param_list:
            if len(p.strip())>0:
              clear_param_list.append(p.strip())
          log.debug(clear_param_list)
          if len(clear_param_list)>0:
            subj=clear_param_list[0]
          if len(clear_param_list)>1:
            for w in clear_param_list[1:]:
              descr+=w
              descr+=" "
        issue_id=mblr.redmine_new_issue(log,user,subj,descr,project_id)
        if issue_id==None:
          if mba.send_message(log,client,room,"Ошибка заведения задачи") == False:
            log.error("send_message() to user")
            return False
        else:
          if mba.send_notice(log,client,room,u"создал задачу: %(redmine_server)s/issues/%(issue_id)d"%{\
              "redmine_server":conf.redmine_server,\
              "issue_id":issue_id\
              }) == False:
            log.error("send_notice() to user %s"%user)
          
      if data["type"]=="redmine_add_comment":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)

        log.debug("len=%d"%len(message))
        help_text="""Необходимо добавить номер ошибки, к которой добавляете коментарий. Например:
В ответ на какой-либо коментарий введите:
  %(redmine_nick)s add 242
или:
  %(redmine_nick)s добавь к 242
или просто, новое сообщение, как комментарий:
  %(redmine_nick)s добавь к 242 сам текст комментария
  
И текст этого коментария (или файл) добавится как коментарий (или как вложение) к ошибке с id=242

При этом алиасом для "add" может быть: "5","comment","добавь","добавить","добавьте","приложи","приложить","вложение","коментарий","комментарий"
"""%{"redmine_nick":nick_name}

        # выкусываем предлоги:
        new_list=[]
        for w in cmd_words:
          if w in ["в", "to", "к", "on", "in"]:
            log.info("пропускаю предлог: %s"%w)
          else:
            new_list.append(w)
        cmd_words=new_list
        # разбор строки:
        if len(cmd_words)==1:
          if mba.send_message(log,client,room,help_text) == False:
            log.error("send_message() to user")
            return False
          return True
        else:
          log.debug(cmd_words)
          try:
            issue_id=int(cmd_words[1])
          except Exception as e:
            log.warning(get_exception_traceback_descr(e))
            if mba.send_message(log,client,room,help_text) == False:
              log.error("send_message() to user")
              return False

        comment_text=None
        url_file=None
        if reply_to_id!=None:
          # это ответ на сообщение:

          # проверяем тип сообщения, которое процитировал пользователь:
          rooms=client.get_rooms()
          room_object=rooms[room]
          source_event=None
          for event in room_object.events:
            if event["event_id"]==reply_to_id:
              log.debug("исходное сообщение")
              log.debug(json.dumps(event, indent=4, sort_keys=True,ensure_ascii=False))
              source_event=event
              break
          if source_event==None:
            log.warning("can not get reply_source_event")
            if mba.send_message(log,client,room,"Сообщение слишком старое - нет в моём кэше (будет доработано будущем).\nДобавляю только текст из цитирования. Проверьте корректность добавления коментария.") == False:
              log.error("send_message() to user")
              return False
            comment_text="уточнение от пользователя матрицы %s:\n\n%s"%(user,source_message.replace('<br/>','\n'))
          else:
            # получили цитируемое сообщение, анализируем его тип:
            if source_event['content']['msgtype']=='m.image':
              if "v" in source_event['content'] and source_event['content']["v"]=="v2":
                url_file=source_event['content']['file']['url']
              else:
                url_file=source_event['content']['url']
              comment_text="пользователь матрицы %s добавил файл вложения: %s"%(user,source_event["content"]["body"])
            else:
              # цитирование текста:
              comment_text="уточнение от пользователя матрицы %s:\n\n%s"%(user,source_event["content"]["body"].replace('<br/>','\n'))

        else:
          # коментарий дальше в сообщении - после номера:

          # разделяем только один раз (первое слово), а потом берём "второе слово",
          # которое содержит всю оставшуюся строку:
          comment_text="уточнение от пользователя матрицы %s:\n\n"%user
          for w in cmd_words[2:]:
            comment_text+=w
            comment_text+=' '

        if url_file==None:
          # отправляем простой комментарий:
          if mblr.redmine_add_comment(log,user,issue_id,comment_text) == False:
            log.error("mblr.redmine_add_comment()")
            if mba.send_message(log,client,room,"Внутренняя ошибка бота - не смог добавить комментарий") == False:
              log.error("send_message() to user")
              return False
            return False
          else:
            if mba.send_notice(log,client,room,"Успешно добавил коментарий к задаче: %(redmine_server)s/issues/%(issue_id)d"%{\
                "redmine_server":conf.redmine_server,\
                "issue_id":issue_id\
                }) == False:
              log.error("send_notice() to user %s"%user)
          return True
        else:
          # отправляем вложение:
          # получаем данные:

          file_data=mba.get_file(log,client,url_file)
          if file_data==None:
            log.error("mba.get_file(%s)"%url_file)
            if mba.send_message(log,client,room,"Внутренняя ошибка бота - не смог скачать вложение") == False:
              log.error("send_message() to user")
              return False
            return False

          if mblr.redmine_add_attachment(log,user,issue_id,comment_text,source_event["content"]["body"],file_data) == False:
            log.error("mblr.redmine_add_attachment()")
            if mba.send_message(log,client,room,"Внутренняя ошибка бота - не смог добавить вложение") == False:
              log.error("send_message() to user")
              return False
            return False
          else:
            if mba.send_notice(log,client,room,"Успешно добавил вложение к задаче: %(redmine_server)s/issues/%(issue_id)d"%{\
                "redmine_server":conf.redmine_server,\
                "issue_id":issue_id\
                }) == False:
              log.error("send_notice() to user %s"%user)
        

      if data["type"]=="redmine_show_stat":
        log.debug("message=%s"%message)
        log.debug("cmd=%s"%cmd)
        return mblr.redmine_show_stat(log,logic,client,room,user,data,message,cmd)
      #=========================== redmine  - конец =====================================

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
  if room not in memmory:
    return None
  if "env" not in memmory[room]:
    return None
  if env_name not in memmory[room]["env"]:
    return None
  return memmory[room]["env"][env_name]

def get_env_list(room):
  global memmory
  if room not in memmory:
    return None
  if "env" not in memmory[room]:
    return None
  return memmory[room]["env"]

def set_env(room,env_name,env_val):
  global memmory
  if room not in memmory:
    memmory[room]={}
  if "env" not in memmory[room]:
    memmory[room]["env"]={}
  memmory[room]["env"][env_name]=env_val
  return True

def set_state(room,state):
  global memmory
  global logic
  if room not in memmory:
    memmory[room]={}
  memmory[room]["state"]=state
  return True

def reset_room_memmory(room):
  global memmory
  if room in memmory:
    del memmory[room]
  return True

def get_state(log,room):
  global memmory
  global logic
  if room in memmory:
    if "state" not in memmory[room]:
      log.error("memmory corrupt for room %s - can not find 'state' struct"%room)
      return None
    else:
      return memmory[room]["state"]
  else:
    # Иначе возвращаем начальный статус логики:
    return logic

def init(log,rule_file,data):
  global logic
  global memmory
  global data_file

  data_file=data
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

def save_data(log,data):
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

def load_data(log):
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
    save_data(log,data)
  #debug_dump_json_to_file("debug_data_as_json.json",data)
  return data

def get_exception_traceback_descr(e):
  tb_str = traceback.format_exception(etype=type(e), value=e, tb=e.__traceback__)
  result=""
  for msg in tb_str:
    result+=msg
  return result

def is_room_public(log,client,room):
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
