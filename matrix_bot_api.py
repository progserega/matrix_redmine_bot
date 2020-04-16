#!/usr/bin/env python
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
import pickle
import re
import requests
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

from matrix_client.client import MatrixClient
from matrix_client.api import MatrixRequestError
from matrix_client.api import MatrixHttpLibError
from requests.exceptions import MissingSchema
import config as conf

def send_report(log,client,user,room,report_url,content_type="application/vnd.ms-excel"):
  log.debug("send_report(%s,%s,%s)"%(user,room,report_url))
  time_now=time.time()
  num=0
#html="<p><strong>Я напомню Вам о следующих событиях:</strong></p>\n<ul>\n"
#  html+="</ul>\n<p><em>Надеюсь ничего не забыл :-)</em></p>\n"
  send_message(log, client, room,u"Формирую файл...")

#f=open("отчёт.xlsx","r")
#data=f.read()
#f.close()
  try:
    response = requests.get(report_url, stream=True)
    data = response.raw      # a `bytes` object
  except:
    log.error("fetch report data from url: %s"%report_url)
    send_message(log, client, room,u"Внутренняя ошибка сервера (не смог получить данные отчёта с сервера отчётов) - обратитесь к администратору")
    return False
    
#send_message(log, client, room,u"Файл готов, загружаю...")
  mxc_url=upload_file(log,client,data,content_type)
  if mxc_url == None:
    log.error("uload file to matrix server")
    send_message(log, client, room,u"Внутренняя ошибка сервера (не смог загрузить файл отчёта на сервер MATRIX) - обратитесь к администратору")
    return False
  log.debug("send file 1")
  if send_file(log, client, room,mxc_url,"Отчёт по ЗЭС.xlsx") == False:
    log.error("send file to room")
    send_message(log, client, room,u"Внутренняя ошибка сервера (не смог отправить файл в комнату пользователю) - обратитесь к администратору")
    return False
  return True


def send_file(log,client,room_id,url,name):
  ret=None
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    log.debug("send file 2")
#ret=room.send_file(url,name,fileinfo)
    ret=room.send_file(url,name)
    log.debug("send file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR send file")
      return False
    else:
      log.error("Couldn't send file (unknown error)")
      return False
  return True

def upload_file(log,client,content,content_type,filename=None):
  log.debug("upload file 1")
  ret=None
  try:
    log.debug("upload file 2")
    ret=client.upload(content,content_type)
    log.debug("upload file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR upload file")
      return None
    else:
      log.error("Couldn't upload file (unknown error)")
      return None
  return ret

def send_html(log,client, room_id, html):
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_html(html)
  except:
    log.error("Unknown error at send message '%s' to room '%s'"%(html,room_id))
    return False
  return True

def send_message(log, client, room_id,message):
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_text(message)
  except:
    log.error("Unknown error at send message '%s' to room '%s'"%(message,room_id))
    return False
  return True

def send_notice(log, client, room_id,message):
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    room.send_notice(message)
  except:
    log.error("Unknown error at send notice message '%s' to room '%s'"%(message,room_id))
    return False
  return True

def send_image(log,client,room,name,image_data):
  # FIXME добавить определение типа:
  mimetype="image/jpeg"
  size=len(image_data)
    
  mxc_url=upload_file(log,client,image_data,mimetype)
  if mxc_url == None:
    log.error("uload file to matrix server")
    return False
  log.debug("upload image file success")

  if matrix_send_image(log,client,room,mxc_url,name,mimetype,size) == False:
    log.error("send file to room")
    return False
  return True

def matrix_send_image(log,client,room_id,url,name,mimetype,size):
  ret=None
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  imageinfo={}
  imageinfo["mimetype"]=mimetype
  imageinfo["size"]=size
  #imageinfo["h"]=height
  #imageinfo["w"]=width
  try:
    log.debug("send file 2")
    ret=room.send_image(url,name,imageinfo=imageinfo)
    #ret=room.send_image(url,name)
    log.debug("send file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR send image with mxurl=%s"%url)
      return False
    else:
      log.error("Couldn't send image (unknown error) with mxurl=%s"%url)
      return False
  return True


def send_file(log,client,room_id,url,name):
  ret=None
  room=None
  try:
    room = client.join_room(room_id)
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("Room ID/Alias in the wrong format")
      return False
    else:
      log.error("Couldn't find room.")
      return False
  try:
    log.debug("send file 2")
#ret=room.send_file(url,name,fileinfo)
    ret=room.send_file(url,name)
    log.debug("send file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR send file")
      return False
    else:
      log.error("Couldn't send file (unknown error)")
      return False
  return True

def upload_file(log,client,content,content_type,filename=None):
  log.debug("upload file 1")
  ret=None
  try:
    log.debug("upload file 2")
    ret=client.upload(content,content_type)
    log.debug("upload file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR upload file")
      return None
    else:
      log.error("Couldn't upload file (unknown error)")
      return None
  return ret

def get_file(log,client,mxurl):
  log.debug("get_file 1")
  ret=None
  # получаем глобальную ссылку на файл:
  try:
    log.debug("get_file file 2")
    full_url=client.api.get_download_url(mxurl)
    log.debug("get_file file 3")
  except MatrixRequestError as e:
    log.error(e)
    if e.code == 400:
      log.error("ERROR download file")
      return None
    else:
      log.error("Couldn't download file (unknown error)")
      return None
  # скачиваем файл по ссылке:
  try:
    response = requests.get(full_url, stream=True)
    data = response.content      # a `bytes` object
  except:
    log.error("fetch file data from url: %s"%full_url)
    return None
  return data

def get_event(log, client, room_id, event_id):
  log.debug("=== start function ===")
  """Perform GET /rooms/$room_id/event/$event_id

  Args:
      room_id(str): The room ID.
      event_id(str): The event ID.

  Raises:
      MatrixRequestError(code=404) if the event is not found.
  """
  return client.api._send("GET", "/rooms/{}/event/{}".format(quote(room_id), quote(event_id)))
