"""Automated tests only. Never select this module on Render."""
from .settings import *
KPN_ENV='test'
IS_PRODUCTION=False
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']
STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}
