import ntplib
from time import ctime

# https://www.codeday.top/2017/01/11/21790.html
# https://stackoverflow.com/questions/24307298/get-actual-time-from-ntp-safe-offset-use-it-in-the-whole-program
#

ntp_client = ntplib.NTPClient()
response = ntp_client.request('europe.pool.ntp.org', version=3)

print "Offset in seconds NOT milliseconds!!!: %s" % response.offset
print "Version %s" % response.version

# TODO: Try to set the system clock if the offset is more than 30 ms
# TODO: Send a Warning E-Mail if the time can not be set or there is still an offset after setting the time
