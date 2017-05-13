import base64

from smtplib import SMTPHeloError, SMTP, SMTPRecipientsRefused, SMTPSenderRefused, SMTPDataError, \
    SMTPAuthenticationError
from threading import Thread

from lampost.di.app import on_app_start
from lampost.di.resource import Injected, module_inject

log = Injected('log')
json_decode = Injected('json_decode')
module_inject(__name__)

available = False
params = {}


@on_app_start
def _start():
    global available
    info_file = None
    try:
        info_file = open('data/email.json', encoding='utf-8')
        for key, value in json_decode(info_file.read()).items():
            params[key] = value
        available = True
    except Exception:
        log.warn("No email info available", exc_info=True)
    if info_file:
        info_file.close()


def _get_oauth_info():
    from oauth2client.service_account import ServiceAccountCredentials
    scopes = ['https://mail.google.com/']
    credentials = ServiceAccountCredentials.from_json_keyfile_name('data/google_api.json',
                                                                   scopes=scopes).create_delegated(
        "lampostmessage@gmail.com")
    access_token_info = credentials.get_access_token()
    access_token = bytes(access_token_info.access_token, 'ascii')
    log.info(access_token)
    return credentials.service_account_email, access_token


def send_targeted_email(subject, text, users):
    if not available:
        return "Email not available"
    wrappers = []
    for user in users:
        if user.email:
            wrappers.append(EmailWrapper(user.email, "\From: {}\nTo: {}\nSubject:{}\n\n{}".
                                         format(params['sender_name'], user.user_name, subject, text)))
        else:
            log.warn("User {} has no email address", user.user_name)
    MessageSender(wrappers).start()
    return "Email Sent"


class MessageSender(Thread):
    def __init__(self, wrappers):
        super().__init__()
        self.wrappers = wrappers

    def run(self):
        if self._open_server():
            for wrapper in self.wrappers:
                self._send_message(wrapper.addresses, wrapper.message)
            self.server.close()

    def _send_message(self, addresses, message):
        try:
            self.server.sendmail(params['sender_email_address'], addresses, message)
        except SMTPHeloError:
            log.exception("Helo error sending email", exc_info=True)
        except SMTPRecipientsRefused:
            log.warn("Failed to send email to {}".format(addresses))
        except SMTPSenderRefused:
            log.warn("Sender refused for email", exc_info=True)
        except SMTPDataError as exp:
            log.exception("Unexpected Data error sending email")

    def _open_server(self):
        self.server = SMTP(params['smtp_server'], params.get("smtp_port", 587))
        self.server.ehlo()
        self.server.starttls()
        if params.get('use_gmail_oauth2'):
            auth_email, access_token = _get_oauth_info()
            auth_string = b'user=' + bytes(params['sender_email_address'],
                                           'ascii') + b'\1auth=Bearer ' + access_token + b'\1\1'
            log.info(auth_string)
            code, msg = self.server.docmd('AUTH', 'XOAUTH2 ' + (base64.b64encode(auth_string)).decode('ascii'))
            log.info("Code {}  Message {}", code, base64.decodebytes(msg))
            if code == 235:
                return True
            code, msg = self.server.docmd('')
            log.info("code {}, Message {}", code, msg)
            return False
        try:
            self.server.login(params['sender_email_address'], params['sender_password'])
            return True
        except SMTPAuthenticationError:
            log.warn("SMTP Password Authentication Failed", ex_info=True)
            return False


class EmailWrapper():
    def __init__(self, addresses, message):
        self.addresses = addresses
        self.message = message
