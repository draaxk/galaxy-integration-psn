import logging
import aiohttp
from urllib.parse import parse_qsl, urlsplit
from galaxy.api.errors import AuthenticationRequired, InvalidCredentials, UnknownBackendResponse
from galaxy.http import handle_exception, create_client_session

OAUTH_LOGIN_REDIRECT_URL = "https://www.playstation.com/"

OAUTH_LOGIN_URL = "https://web.np.playstation.com/api/session/v1/signin" \
                  "?redirect_uri=https://io.playstation.com/central/auth/login" \
                  "%3FpostSignInURL={redirect_url}" \
                  "%26cancelURL={redirect_url}" \
                  "&smcid=web:pdc"

OAUTH_LOGIN_URL = OAUTH_LOGIN_URL.format(redirect_url=OAUTH_LOGIN_REDIRECT_URL)


OAUTH_LOGIN_NPSSO = "https://ca.account.sony.com/api/v1/ssocookie"

OAUTH_CODE_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize" \
                    "?access_type=offline" \
                    "&client_id=09515159-7237-4370-9b40-3806e67c0891" \
                    "&redirect_uri=com.scee.psxandroid.scecompcall://redirect" \
                    "&response_type=code&scope=psn:mobile.v2.core psn:clientapp"

OAUTH_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"

REFRESH_COOKIES_URL = OAUTH_LOGIN_URL

DEFAULT_TIMEOUT = 30


class CookieJar(aiohttp.CookieJar):
    def __init__(self):
        super().__init__()
        self._cookies_updated_callback = None

    def set_cookies_updated_callback(self, callback):
        self._cookies_updated_callback = callback

    def update_cookies(self, cookies, *args):
        super().update_cookies(cookies, *args)
        if cookies and self._cookies_updated_callback:
            self._cookies_updated_callback(list(self))


class HttpClient:
    def __init__(self):
        self._cookie_jar = CookieJar()
        self._session = create_client_session(cookie_jar=self._cookie_jar)

    async def close(self):
        await self._session.close()

    async def _request(self, method, url, *args, **kwargs):
        with handle_exception():
            return await self._session.request(method, url, *args, **kwargs)

    async def get(self, url, *args, **kwargs):
        silent = kwargs.pop("silent", False)
        get_json = kwargs.pop("get_json", True)
        response = await self._request("GET", *args, url=url, **kwargs)
        try:
            raw_response = "***" if silent else await response.text()
            logging.debug("Response for:\n{url}\n{data}".format(url=url, data=raw_response))
            return await response.json() if get_json else await response.text()
        except ValueError:
            logging.exception("Invalid response data for:\n{url}".format(url=url))
            raise UnknownBackendResponse()

    async def getWithToken(self, url, *args, **kwargs):
        if not self._access_token:
            raise AuthenticationRequired()
        headers = kwargs.setdefault("headers", {})
        headers["authorization"] = "Bearer " + self._access_token
        return await self.get(url=url, *args, **kwargs)

    async def post(self, url, *args, **kwargs):
        logging.debug("Sending data:\n{url}".format(url=url))
        response = await self._request("POST", *args, url=url, **kwargs)
        logging.debug("Response for post:\n{url}\n{data}".format(url=url, data=await response.text()))
        return response

    def set_cookies_updated_callback(self, callback):
        self._cookie_jar.set_cookies_updated_callback(callback)

    def update_cookies(self, cookies):
        self._cookie_jar.update_cookies(cookies)

    async def refresh_cookies(self):
        await self.get(REFRESH_COOKIES_URL, silent=True, get_json=False)

    async def initToken(self):
        self._access_token = None
        result = await self.get(OAUTH_LOGIN_NPSSO, get_json=True)
        logging.debug(f"NPSSO: {result}")
        try:
            response = await self._request(
                "GET",
                url=OAUTH_CODE_URL,
                cookies=result,
                allow_redirects=False
            )
            location_params = urlsplit(response.headers["Location"])
            logging.debug(f"Location: {location_params}")

            location_query = dict(parse_qsl(location_params.query))
            if "error" in location_query:
                raise AuthenticationRequired(location_query)
            logging.debug(f"Query: {location_query}")
            
            body = {
                "code" : location_query["code"],
                "redirect_uri" : "com.scee.psxandroid.scecompcall://redirect",
                "grant_type" : "authorization_code",
                "token_format" : "jwt"
            }
            headers = {
                "Content-Type" : "application/x-www-form-urlencoded",
                "Authorization" : "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
            }
            
            resultToken = await self.post(url=OAUTH_TOKEN_URL, data=body, headers=headers)
            if resultToken:  
                json = await resultToken.json()
                self._access_token = json["access_token"]
                logging.debug(f"Token: {self._access_token}")
            else:
                logging.error(f"Unable to retreive access token for trophies")
            resultToken.close()

        except AuthenticationRequired as e:
            raise InvalidCredentials(e.data)
        except (KeyError, IndexError):
            raise UnknownBackendResponse(str(response.headers))
        finally:
            if response:
                response.close()