"""Explicit binding/host policy and single-hop local IIS proxy trust."""
import ipaddress,os
from urllib.parse import urlsplit


def configuration():
    from .deployment_settings import load,DEFAULT_HOSTS
    load()
    bind=os.environ.get('CIRRUS_BIND','127.0.0.1');port=int(os.environ.get('CIRRUS_PORT','8000'))
    internal=os.environ.get('CIRRUS_INTERNAL_ACCESS','0')=='1';https=os.environ.get('CIRRUS_HTTPS','0')=='1'
    hosts={x.strip().lower() for x in os.environ.get('CIRRUS_ALLOWED_HOSTS',DEFAULT_HOSTS).split(',') if x.strip()}
    if not hosts or any('*' in x or '/' in x or ':' in x for x in hosts):raise RuntimeError('Set explicit CIRRUS_ALLOWED_HOSTS names without scheme/port/wildcards.')
    if not 1<=port<=65535:raise RuntimeError('Invalid port.')
    if bind not in ('127.0.0.1','::1','localhost') and (not internal or (not https and os.environ.get('CIRRUS_ALLOW_HTTP_LAN')!='1')):
        raise RuntimeError('LAN binding requires explicit internal access and HTTPS, or CIRRUS_ALLOW_HTTP_LAN=1 for restricted testing.')
    proxy=os.environ.get('CIRRUS_TRUSTED_PROXY','')
    if proxy and proxy not in ('127.0.0.1','::1'):raise RuntimeError('Only a configured local reverse proxy can be trusted.')
    return dict(bind=bind,port=port,internal=internal,https=https,hosts=hosts,proxy=proxy)


class LocalProxy:
    def __init__(self,app,proxy):self.app,self.proxy=app,proxy
    def __call__(self,environ,start_response):
        peer=environ.get('REMOTE_ADDR','')
        if self.proxy and peer==self.proxy:
            if environ.get('HTTP_X_FORWARDED_PROTO')=='https':environ['wsgi.url_scheme']='https'
            forwarded=environ.get('HTTP_X_FORWARDED_FOR','')
            try:ipaddress.ip_address(forwarded);environ['REMOTE_ADDR']=forwarded
            except ValueError:pass
        # Forwarded host/port are never trusted. IIS must preserve the original Host.
        for key in list(environ):
            if key.startswith('HTTP_X_FORWARDED_') or key=='HTTP_FORWARDED':environ.pop(key,None)
        return self.app(environ,start_response)
