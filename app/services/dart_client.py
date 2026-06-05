from dataclasses import dataclass
from io import BytesIO
from typing import Any, ClassVar
from xml.etree import ElementTree
from zipfile import ZipFile

import httpx


@dataclass(frozen=True)
class DARTEndpointResult:
    """Result for one DART endpoint call.

    DART failures are represented as data=None with an error string so callers can
    continue returning partial stock research results.
    """

    data: dict[str, Any] | list[dict[str, Any]] | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class DARTClient:
    """OpenDART client for Korean disclosure and financial statement data."""

    _corp_code_mapping_cache: ClassVar[dict[str, dict[str, Any]] | None] = None

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://opendart.fss.or.kr/api",
        timeout_seconds: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def get_corp_code_mapping(self) -> DARTEndpointResult:
        if DARTClient._corp_code_mapping_cache is not None:
            return DARTEndpointResult(data=DARTClient._corp_code_mapping_cache)
        if not self.api_key:
            return DARTEndpointResult(data=None, error="DART_API_KEY is not configured")

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get("/corpCode.xml", params={"crtfc_key": self.api_key})
                response.raise_for_status()
                mapping = self._parse_corp_code_zip(response.content)
        except httpx.TimeoutException:
            return DARTEndpointResult(data=None, error="DART timeout for /corpCode.xml")
        except httpx.HTTPStatusError as exc:
            return DARTEndpointResult(
                data=None,
                error=f"DART HTTP {exc.response.status_code} for /corpCode.xml",
            )
        except httpx.HTTPError as exc:
            return DARTEndpointResult(
                data=None, error=f"DART network error for /corpCode.xml: {exc}"
            )
        except (ElementTree.ParseError, IndexError, KeyError, ValueError) as exc:
            return DARTEndpointResult(
                data=None, error=f"DART corp code parse error for /corpCode.xml: {exc}"
            )

        DARTClient._corp_code_mapping_cache = mapping
        return DARTEndpointResult(data=mapping)

    async def find_corp_by_stock_code(self, stock_code: str) -> DARTEndpointResult:
        normalized_stock_code = stock_code.zfill(6)
        mapping_result = await self.get_corp_code_mapping()
        if not mapping_result.ok or not isinstance(mapping_result.data, dict):
            return mapping_result
        corp = mapping_result.data.get(normalized_stock_code)
        if not isinstance(corp, dict):
            return DARTEndpointResult(
                data=None,
                error=f"DART corp code not found for stock code {normalized_stock_code}",
            )
        return DARTEndpointResult(data=corp)

    async def get_company_overview(self, stock_code: str) -> DARTEndpointResult:
        corp_result = await self.find_corp_by_stock_code(stock_code)
        if not corp_result.ok or not isinstance(corp_result.data, dict):
            return corp_result
        corp_code = str(corp_result.data["corp_code"])
        result = await self._get_json_endpoint("/company.json", {"corp_code": corp_code})
        if result.ok and isinstance(result.data, dict):
            merged = {**corp_result.data, **result.data}
            return DARTEndpointResult(data=merged)
        return result

    async def get_financial_statement(
        self, stock_code: str, year: int | str, report_code: str
    ) -> DARTEndpointResult:
        corp_result = await self.find_corp_by_stock_code(stock_code)
        if not corp_result.ok or not isinstance(corp_result.data, dict):
            return corp_result
        corp_code = str(corp_result.data["corp_code"])
        return await self._get_json_list_endpoint(
            "/fnlttSinglAcnt.json",
            {
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": report_code,
            },
        )

    async def get_recent_filings(self, stock_code: str, limit: int = 20) -> DARTEndpointResult:
        corp_result = await self.find_corp_by_stock_code(stock_code)
        if not corp_result.ok or not isinstance(corp_result.data, dict):
            return corp_result
        corp_code = str(corp_result.data["corp_code"])
        return await self._get_json_list_endpoint(
            "/list.json",
            {
                "corp_code": corp_code,
                "page_no": 1,
                "page_count": max(1, min(limit, 100)),
            },
        )

    async def _get_json_list_endpoint(
        self, path: str, params: dict[str, str | int]
    ) -> DARTEndpointResult:
        result = await self._get_json_endpoint(path, params)
        if not result.ok:
            return result
        if isinstance(result.data, dict):
            payload = result.data.get("list", [])
            if isinstance(payload, list):
                return DARTEndpointResult(data=payload)
        return DARTEndpointResult(data=None, error=f"DART missing list payload for {path}")

    async def _get_json_endpoint(
        self, path: str, params: dict[str, str | int]
    ) -> DARTEndpointResult:
        if not self.api_key:
            return DARTEndpointResult(data=None, error="DART_API_KEY is not configured")

        request_params: dict[str, str | int] = {"crtfc_key": self.api_key}
        request_params.update(params)

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = await client.get(path, params=request_params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException:
            return DARTEndpointResult(data=None, error=f"DART timeout for {path}")
        except httpx.HTTPStatusError as exc:
            return DARTEndpointResult(
                data=None,
                error=f"DART HTTP {exc.response.status_code} for {path}",
            )
        except httpx.HTTPError as exc:
            return DARTEndpointResult(data=None, error=f"DART network error for {path}: {exc}")
        except ValueError:
            return DARTEndpointResult(data=None, error=f"DART returned invalid JSON for {path}")

        if not isinstance(payload, dict):
            return DARTEndpointResult(
                data=None, error=f"DART returned unsupported payload for {path}"
            )
        if self._is_dart_error_payload(payload):
            return DARTEndpointResult(
                data=None,
                error=f"DART API {payload.get('status')} for {path}: {payload.get('message')}",
            )
        return DARTEndpointResult(data=payload)

    def _parse_corp_code_zip(self, content: bytes) -> dict[str, dict[str, Any]]:
        with ZipFile(BytesIO(content)) as archive:
            xml_name = archive.namelist()[0]
            xml_content = archive.read(xml_name)
        root = ElementTree.fromstring(xml_content)
        mapping: dict[str, dict[str, Any]] = {}
        for item in root.findall("list"):
            stock_code = (item.findtext("stock_code") or "").strip()
            if not stock_code:
                continue
            mapping[stock_code] = {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": stock_code,
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
        return mapping

    def _is_dart_error_payload(self, payload: dict[str, Any]) -> bool:
        status = payload.get("status")
        return status not in (None, "000")
