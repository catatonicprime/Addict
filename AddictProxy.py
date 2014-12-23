from gevent import httplib

__author__ = 'catatonic'

from twisted.web import http
from twisted.internet import reactor, protocol
from twisted.python import log
import httplib2
from urlparse import urlparse
import cookielib
import urllib2

class AddictProxy(http.HTTPClient):
    def __init__(self, method, uri, data, headers, original):
        self.method = method
        path = urlparse(uri).path
        self.uri = path
        self.data = data
        self.headers = headers
        self.original = original
        self.length = None

    def sendRequest(self):
        log.msg("Sending request: %s %s" % (self.method, self.uri))
        self.sendCommand(self.method, self.uri)

    def sendHeaders(self):
        for key, values in self.headers:
            if key.lower() == 'connection':
                values = ['close']
            elif key.lower() == 'keep-alive':
                next

            for value in values:
                self.sendHeader(key, value)
        self.endHeaders()

    def sendPostData(self):
        log.msg("Sending POST data")
        self.transport.write(self.data)

    def connectionMade(self):
        log.msg("HTTP connection made")
        self.sendRequest()
        self.sendHeaders()
        if self.method == 'POST':
            self.sendPostData()

    def handleStatus(self, version, code, message):
        log.msg("Got server response: %s %s %s" % (version, code, message))
        self.original.setResponseCode(int(code), message)

    def handleHeader(self, key, value):
        if key.lower() == 'content-length':
            self.length = value
        else:
            self.original.responseHeaders.addRawHeader(key, value)

    def handleResponse(self, data):
        data = self.original.processResponse(data)

        if self.length != None:
            self.original.setHeader('Content-Length', len(data))

        self.original.write(data)

        try:
            self.original.finish()
        except:
            print "failed to 'finish'"
        self.transport.loseConnection()

class ProxyClientFactory(protocol.ClientFactory):
    def __init__(self, method, uri, data, headers, original):
        self.protocol = AddictProxy
        self.method = method
        self.uri = uri
        self.data = data
        self.headers = headers
        self.original = original

    def buildProtocol(self, addr):
        return self.protocol(self.method, self.uri, self.data,
                             self.headers, self.original)

    def clientConnectionFailed(self, connector, reason):
        log.err("Server connection failed: %s" % reason)
        self.original.setResponseCode(504)
        self.original.finish()


class ProxyRequest(http.Request):
    def __init__(self, channel, queued, reactor=reactor):
        http.Request.__init__(self, channel, queued)
        self.reactor = reactor

    def process(self):
        host = self.getHeader('host')
        if not host:
            log.err("No host header given")
            self.setResponseCode(400)
            self.finish()
            return

        port = 80
        if ':' in host:
            host, port = host.split(':')
            port = int(port)

        self.setHost(host, port)

        self.content.seek(0, 0)
        postData = self.content.read()
        factory = ProxyClientFactory(self.method, self.uri, postData,
                                     self.requestHeaders.getAllRawHeaders(),
                                     self)
        self.reactor.connectTCP(host, port, factory)

    def processResponse(self, data):
        if self.responseHeaders.hasHeader('location'):
            uri = self.responseHeaders.getRawHeaders('location')[0] #there is a redirect, follow it!
            print self.responseHeaders
            url = urlparse(uri)
            if url.scheme == 'https':
                '''
                non-plaintext, let's try to:
                1) fixate the session
                2) check if the session is fixated for N of minutes ever M seconds (default 10, every 60 minutes)
                '''
                print "[*] redirect identified: " + uri
                response = urllib2.urlopen(uri)
                print "[*] finalized url after redirects: " + response.geturl()
                cookies = response.info().getheader('set-cookie')
                if cookies is not None:
                    print "* Attempting to fixate for session:\n\t" + str(cookies)
                    self.setHeader('set-cookie', cookies)
        #self.setResponseCode(200)
        return data


class TransparentProxy(http.HTTPChannel):
    requestFactory = ProxyRequest

class ProxyFactory(http.HTTPFactory):
    protocol = TransparentProxy

reactor.listenTCP(10001, ProxyFactory())
reactor.run()