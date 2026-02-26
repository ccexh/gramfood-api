import json
import logging
import secrets

import httpx

from .errors import SMSSendError
from ..config import config

logger = logging.getLogger(__name__)


class SMSProviderClient:
    """The client for sms.ir SMS provider API interactions."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.sms.ir/v1",
            transport=httpx.AsyncHTTPTransport(http2=True),
            headers={"User-Agent": "", "X-API-KEY": config["sms"]["api_key"]},
            timeout=httpx.Timeout(timeout=abs(config["main"]["request_timeout"])),
        )

    async def send_otp(self, phone: str, code: str) -> int:
        """Sends an OTP code via the SMS provider.

        Returns:
            The message ID from the SMS provider.

        Raises:
            ``SMSSendError``:
                If the SMS provider fails to send the OTP.
        """
        content = {
            "mobile": phone,
            "templateId": config["sms"]["template_id"],
            "parameters": [{"name": "OTP", "value": code}],
        }

        if config["main"]["development"]:
            message_id = secrets.randbelow(10**10)
            logger.debug(f"Simulated OTP send | phone={phone} code={code}")
        else:
            try:
                response = await self._client.post(
                    "/send/verify",
                    headers={"Content-Type": "application/json"},
                    content=json.dumps(content).encode(),
                )
            except httpx.HTTPError as error:
                raise SMSSendError(
                    phone, payload={"phone": phone, "request": content}
                ) from error

            data = json.loads(response.content)
            if response.status_code != 200 or data.get("status") != 1:
                raise SMSSendError(
                    phone,
                    payload={"phone": phone, "request": content, "response": data},
                )

            data = data["data"]
            message_id = data["messageId"]
            logger.info(
                f"OTP SMS sent | phone={phone} message_id={message_id} cost={data['cost']}"
            )

        return message_id
