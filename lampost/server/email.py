from smtplib import SMTPHeloError, SMTP, SMTPRecipientsRefused, SMTPSenderRefused, SMTPDataError
from threading import Thread

from lampost.di.resource import Injected, module_inject

log = Injected('log')
module_inject(__name__)


class EmailSender():
    def __init__(self):
        try:
            info_file = open('data/email_info')
        except IOError:
            log.warn("No email info available")
            self.available = False
            return
        email_info = info_file.readlines()
        self.email_name = email_info[0].strip
        self.email_address = email_info[1].strip()
        self.email_password = email_info[2].strip()
        info_file.close()
        self.available = True

    def send_targeted_email(self, subject, text, users):
        if not self.available:
            return "Email not available"
        wrappers = []
        for user in users:
            if user.email:
                wrappers.append(EmailWrapper(user.email, "\From: {}\nTo: {}\nSubject:{}\n\n{}".format(self.email_name, user.user_name, subject, text)))
            else:
                log.warn("User {} has no email address", user.user_name)
        MessageSender(wrappers).start()
        return "Email Sent"


email_sender = EmailSender()


class MessageSender(Thread):
    def __init__(self, wrappers):
        super().__init__()
        self.wrappers = wrappers

    def run(self):
        self._open_server()
        for wrapper in self.wrappers:
            self._send_message(wrapper.addresses, wrapper.message)
        self.server.close()

    def _send_message(self, addresses, message):
        try:
            self.server.sendmail(self.email_sender.email_address, addresses, message)
        except SMTPHeloError:
            log.exception("Helo error sending email")
        except SMTPRecipientsRefused:
            log.warn("Failed to send email to {}".format(addresses))
        except SMTPSenderRefused:
            log.warn("Sender refused for email")
        except SMTPDataError as exp:
            log.exception("Unexpected Data error sending email")

    def _open_server(self):
        self.server = SMTP("smtp.gmail.com", 587)
        self.server.ehlo()
        self.server.starttls()
        self.server.login(self.email_sender.email_address, self.email_sender.email_password)


class EmailWrapper():
    def __init__(self, addresses, message):
        self.addresses = addresses
        self.message = message
