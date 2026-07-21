from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse

try:
    from playwright.async_api import BrowserContext, Page, async_playwright
except ImportError:
    print("Playwright가 설치되지 않았습니다. 먼저 01_INSTALL.bat을 실행하세요.")
    raise

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
PRIVATE_DIR = ROOT / "private"
PROFILE_DIR = PRIVATE_DIR / "browser_profile"
DATA_DIR = ROOT / "data"
CATALOG_JSON = DATA_DIR / "catalog.json"
INDEX_HTML = ROOT / "index.html"
DETAIL_HTML = ROOT / "detail.html"
DEBUG_HTML = PRIVATE_DIR / "debug_collection.html"
DEBUG_SCREENSHOT = PRIVATE_DIR / "debug_collection.png"
DEBUG_INFO = PRIVATE_DIR / "debug_info.json"
KST = timezone(timedelta(hours=9))
LOGIN_REQUIRED_TEXTS = (
    "商品を閲覧するにはログインが必要です",
    "로그인이 필요",
    "login is required",
)


class CatalogError(RuntimeError):
    pass


@dataclass
class Settings:
    collection_url: str
    collection_json_url: str
    site_title: str
    refresh_minutes: int
    browser_channel: str
    headless_collect: bool
    max_pages: int
    page_limit: int
    request_delay_seconds: float
    product_delay_seconds: float
    git_branch: str
    github_pages_base_url: str


def load_settings() -> Settings:
    if not CONFIG_PATH.exists():
        raise CatalogError(f"설정 파일이 없습니다: {CONFIG_PATH}")
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return Settings(
        collection_url=str(data.get("collection_url", "")).strip(),
        collection_json_url=str(data.get("collection_json_url", "")).strip(),
        site_title=str(data.get("site_title", "ISSEY MIYAKE SPECIAL PRICE")).strip(),
        refresh_minutes=max(1, int(data.get("refresh_minutes", 5))),
        browser_channel=str(data.get("browser_channel", "chrome")).strip(),
        headless_collect=bool(data.get("headless_collect", True)),
        max_pages=max(1, int(data.get("max_pages", 20))),
        page_limit=max(1, int(data.get("page_limit", 250))),
        request_delay_seconds=max(0.0, float(data.get("request_delay_seconds", 0.35))),
        product_delay_seconds=max(0.0, float(data.get("product_delay_seconds", 0.15))),
        git_branch=str(data.get("git_branch", "main")).strip() or "main",
        github_pages_base_url=str(data.get("github_pages_base_url", "")).strip(),
    )


def log(message: str) -> None:
    now = datetime.now(KST).strftime("%H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def ensure_dirs() -> None:
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


async def launch_context(playwright: Any, settings: Settings, *, headless: bool) -> BrowserContext:
    kwargs: dict[str, Any] = {
        "user_data_dir": str(PROFILE_DIR),
        "headless": headless,
        "viewport": {"width": 1440, "height": 1000},
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    channel = settings.browser_channel or ""
    if channel:
        try:
            return await playwright.chromium.launch_persistent_context(channel=channel, **kwargs)
        except Exception as exc:
            log(f"설정된 브라우저 채널({channel}) 실행 실패. Playwright Chromium으로 재시도: {exc}")
    return await playwright.chromium.launch_persistent_context(**kwargs)


async def get_page(context: BrowserContext) -> Page:
    pages = context.pages
    return pages[0] if pages else await context.new_page()


async def goto_collection(page: Page, settings: Settings) -> None:
    await page.goto(settings.collection_url, wait_until="domcontentloaded", timeout=90_000)
    await page.wait_for_timeout(2500)


async def body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=10_000)
    except Exception:
        return ""


async def save_debug(page: Page, extra: dict[str, Any] | None = None) -> None:
    ensure_dirs()
    try:
        DEBUG_HTML.write_text(await page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        await page.screenshot(path=str(DEBUG_SCREENSHOT), full_page=True)
    except Exception:
        pass
    info = {
        "saved_at": datetime.now(KST).isoformat(),
        "url": page.url,
        "title": await page.title(),
        "extra": extra or {},
    }
    DEBUG_INFO.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


async def fetch_same_origin_json(page: Page, url: str) -> tuple[int, str, Any | None]:
    result = await page.evaluate(
        """
        async (url) => {
          try {
            const response = await fetch(url, {
              method: 'GET',
              credentials: 'include',
              cache: 'no-store',
              headers: {'Accept': 'application/json,text/plain,*/*'}
            });
            const text = await response.text();
            return {status: response.status, text};
          } catch (error) {
            return {status: 0, text: String(error)};
          }
        }
        """,
        url,
    )
    status = int(result.get("status", 0))
    text = str(result.get("text", ""))
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return status, text, parsed


def with_query(url: str, **params: Any) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({k: str(v) for k, v in params.items()})
    return urlunparse(parsed._replace(query=urlencode(query)))


async def fetch_collection_products(page: Page, settings: Settings) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page_number in range(1, settings.max_pages + 1):
        url = with_query(
            settings.collection_json_url,
            limit=settings.page_limit,
            page=page_number,
            _ts=int(time.time()),
        )
        status, text, parsed = await fetch_same_origin_json(page, url)
        if status != 200 or not isinstance(parsed, dict):
            log(f"인증 products.json 응답 실패: page={page_number}, status={status}")
            if page_number == 1:
                snippet = text[:400].replace("\n", " ")
                log(f"응답 일부: {snippet}")
            break
        page_products = parsed.get("products")
        if not isinstance(page_products, list) or not page_products:
            log(f"products.json page={page_number}: 0개")
            break
        new_count = 0
        for item in page_products:
            key = str(item.get("id") or item.get("handle") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            products.append(item)
            new_count += 1
        log(f"products.json page={page_number}: {len(page_products)}개, 신규 {new_count}개")
        if len(page_products) < settings.page_limit or new_count == 0:
            break
        await asyncio.sleep(settings.request_delay_seconds)
    return products


async def extract_product_links(page: Page, settings: Settings) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    total_hint = None
    text = await body_text(page)
    match = re.search(r"/\s*([0-9,]+)\s*件", text)
    if match:
        total_hint = int(match.group(1).replace(",", ""))
    estimated_pages = min(
        settings.max_pages,
        max(1, ((total_hint or 48) + 47) // 48),
    )
    log(f"DOM 대체 수집 시작: 예상 {estimated_pages}페이지")
    for number in range(1, estimated_pages + 1):
        url = with_query(settings.collection_url, page=number)
        await page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(2200)
        hrefs = await page.locator('a[href*="/products/"]').evaluate_all(
            "els => els.map(e => e.href).filter(Boolean)"
        )
        before = len(links)
        for href in hrefs:
            clean = str(href).split("?")[0].split("#")[0]
            if "/products/" not in clean or clean in seen:
                continue
            seen.add(clean)
            links.append(clean)
        log(f"컬렉션 page={number}: 상품 링크 신규 {len(links)-before}개")
        await asyncio.sleep(settings.request_delay_seconds)
    return links


async def fetch_product_from_link(page: Page, product_url: str) -> dict[str, Any] | None:
    parsed = urlparse(product_url)
    handle = parsed.path.rstrip("/").split("/")[-1]
    if not handle:
        return None
    candidates = [
        urljoin(product_url, f"/products/{handle}.js"),
        urljoin(product_url, f"/products/{handle}.json"),
    ]
    for candidate in candidates:
        status, _, parsed_data = await fetch_same_origin_json(page, candidate)
        if status != 200 or not isinstance(parsed_data, dict):
            continue
        if isinstance(parsed_data.get("product"), dict):
            product = dict(parsed_data["product"])
            product["_price_minor_units"] = candidate.endswith(".js")
            return product
        if parsed_data.get("handle") or parsed_data.get("title"):
            product = dict(parsed_data)
            product["_price_minor_units"] = candidate.endswith(".js")
            return product
    return None


async def fetch_products_from_links(page: Page, links: list[str], settings: Settings) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for index, link in enumerate(links, start=1):
        item = await fetch_product_from_link(page, link)
        if item:
            products.append(item)
        if index == 1 or index % 20 == 0 or index == len(links):
            log(f"상품 상세 수집 {index}/{len(links)} (성공 {len(products)})")
        await asyncio.sleep(settings.product_delay_seconds)
    return products


def image_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("src") or value.get("url") or "")
    return ""


def normalize_money(value: Any, *, minor_units: bool = False) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    # Shopify product.js exposes integer minor units. products.json normally exposes decimal strings.
    if minor_units:
        return int(round(number / 100))
    return int(round(number))


def normalize_product(raw: dict[str, Any], settings: Settings) -> dict[str, Any]:
    handle = str(raw.get("handle") or "").strip()
    product_url = urljoin(settings.collection_url, f"/products/{handle}") if handle else ""

    images_raw = raw.get("images") or []
    images: list[str] = []
    for item in images_raw:
        src = image_url(item)
        if not src:
            continue
        absolute = urljoin(settings.collection_url, src)
        if absolute not in images:
            images.append(absolute)

    featured = image_url(raw.get("featured_image")) or image_url(raw.get("image"))
    if featured:
        featured = urljoin(settings.collection_url, featured)
        if featured not in images:
            images.insert(0, featured)
    elif images:
        featured = images[0]

    minor_units = bool(raw.get("_price_minor_units"))
    variants_out: list[dict[str, Any]] = []
    for variant in raw.get("variants") or []:
        available = variant.get("available") is True
        title = str(variant.get("title") or "옵션")
        if title == "Default Title":
            title = "기본 옵션"
        variants_out.append(
            {
                "id": str(variant.get("id") or ""),
                "title": title,
                "sku": str(variant.get("sku") or ""),
                "available": available,
                "price": normalize_money(variant.get("price"), minor_units=minor_units),
                "compare_at_price": normalize_money(variant.get("compare_at_price"), minor_units=minor_units),
                "option1": variant.get("option1"),
                "option2": variant.get("option2"),
                "option3": variant.get("option3"),
            }
        )

    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]

    options_raw = raw.get("options") or []
    options: list[dict[str, Any]] = []
    for index, option in enumerate(options_raw, start=1):
        if isinstance(option, dict):
            name = str(option.get("name") or f"Option {index}")
            values = option.get("values") or []
        else:
            name = str(option or f"Option {index}")
            values = []
        options.append({"name": name, "values": [str(value) for value in values]})

    description_html = str(raw.get("body_html") or raw.get("description") or "").strip()

    return {
        "id": str(raw.get("id") or handle),
        "handle": handle,
        "title": str(raw.get("title") or "상품명 없음"),
        "vendor": str(raw.get("vendor") or "ISSEY MIYAKE"),
        "product_type": str(raw.get("product_type") or raw.get("type") or ""),
        "url": product_url,
        "image": featured,
        "images": images,
        "description_html": description_html,
        "options": options,
        "tags": tags,
        "published_at": str(raw.get("published_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
        "variants": variants_out,
        "available": any(v["available"] for v in variants_out),
    }


def load_previous_products() -> dict[str, dict[str, Any]]:
    if not CATALOG_JSON.exists():
        return {}
    try:
        payload = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for product in payload.get("products") or []:
        if not isinstance(product, dict):
            continue
        key = str(product.get("handle") or product.get("id") or "")
        if key:
            result[key] = product
    return result


def merge_cached_detail(product: dict[str, Any], cached: dict[str, Any] | None) -> dict[str, Any]:
    if not cached:
        return product
    for field in ("description_html", "images", "image", "options", "product_type", "tags"):
        if not product.get(field) and cached.get(field):
            product[field] = cached[field]
    return product


async def enrich_product_details(
    page: Page,
    products: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    previous = load_previous_products()
    enriched: list[dict[str, Any]] = []
    fetched = 0
    for index, product in enumerate(products, start=1):
        key = str(product.get("handle") or product.get("id") or "")
        product = merge_cached_detail(product, previous.get(key))
        needs_fetch = not product.get("description_html") or len(product.get("images") or []) < 2
        if needs_fetch and product.get("url"):
            detail_raw = await fetch_product_from_link(page, str(product["url"]))
            if detail_raw:
                detail = normalize_product(detail_raw, settings)
                for field in ("description_html", "images", "image", "options", "product_type", "tags"):
                    if detail.get(field):
                        product[field] = detail[field]
                if detail.get("variants"):
                    product["variants"] = detail["variants"]
                    product["available"] = detail["available"]
                fetched += 1
            await asyncio.sleep(settings.product_delay_seconds)
        enriched.append(product)
        if index == 1 or index % 25 == 0 or index == len(products):
            log(f"상세정보 보강 {index}/{len(products)} (추가 조회 {fetched})")
    return enriched


def product_sort_key(product: dict[str, Any]) -> tuple[Any, ...]:
    return (
        not product.get("available", False),
        product.get("vendor", ""),
        product.get("title", ""),
    )


def yen(value: int | None) -> str:
    return "-" if value is None else f"¥{value:,}"


def product_prices(product: dict[str, Any]) -> tuple[int | None, int | None]:
    variants = product.get("variants") or []
    prices = [v.get("price") for v in variants if isinstance(v.get("price"), int)]
    compares = [v.get("compare_at_price") for v in variants if isinstance(v.get("compare_at_price"), int)]
    return (min(prices) if prices else None, min(compares) if compares else None)


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def build_variant_html(product: dict[str, Any]) -> str:
    variants = product.get("variants") or []
    if not variants:
        return '<div class="empty-variant">옵션 정보 없음</div>'
    rows = []
    for variant in variants:
        available = bool(variant.get("available"))
        row_class = "variant in-stock" if available else "variant out-stock"
        status = "재고 있음" if available else "품절"
        sku = esc(variant.get("sku"))
        sku_html = f'<div class="sku">{sku}</div>' if sku else ""
        price = variant.get("price")
        price_html = f'<span class="variant-price">{esc(yen(price))}</span>' if price is not None else ""
        rows.append(
            f'<div class="{row_class}"><div><div class="variant-name">{esc(variant.get("title"))}</div>{sku_html}</div>'
            f'<div class="variant-right">{price_html}<span class="variant-status">{status}</span></div></div>'
        )
    return "".join(rows)


def build_dashboard(payload: dict[str, Any], settings: Settings) -> str:
    products = sorted(payload.get("products") or [], key=product_sort_key)
    total_products = len(products)
    available_products = sum(1 for p in products if p.get("available"))
    total_variants = sum(len(p.get("variants") or []) for p in products)
    available_variants = sum(
        1 for p in products for v in (p.get("variants") or []) if v.get("available")
    )
    brand_counts = Counter(str(p.get("vendor") or "UNKNOWN") for p in products)
    brand_buttons = [
        f'<button class="brand-button active" data-brand="ALL">전체 <span>{total_products}</span></button>'
    ]
    for brand in sorted(brand_counts):
        brand_buttons.append(
            f'<button class="brand-button" data-brand="{esc(brand)}">{esc(brand)} <span>{brand_counts[brand]}</span></button>'
        )
    cards = []
    for product in products:
        price, compare = product_prices(product)
        compare_html = ""
        if compare is not None and compare != price:
            compare_html = f'<span class="compact-compare">{esc(yen(compare))}</span>'
        image = esc(product.get("image"))
        image_html = (
            f'<img src="{image}" loading="lazy" alt="{esc(product.get("title"))}">'
            if image
            else '<div class="no-image">NO IMAGE</div>'
        )
        variants = product.get("variants") or []
        in_count = sum(1 for v in variants if v.get("available"))
        status_class = "available" if product.get("available") else "soldout"
        status_text = "재고 있음" if product.get("available") else "전체 품절"
        tag_text = ", ".join(str(t) for t in (product.get("tags") or [])[:8])
        updated = esc(product.get("updated_at"))
        product_url = esc(product.get("url"))
        local_detail_url = "detail.html?handle=" + quote(str(product.get("handle") or ""), safe="")
        product_button = (
            f'<a class="button secondary" href="{product_url}" target="_blank" rel="noopener">공식 구매 페이지 · 로그인 필요</a>'
            if product_url
            else ""
        )
        cards.append(
            f'''<article class="card" data-brand="{esc(product.get("vendor"))}" data-available="{str(bool(product.get("available"))).lower()}" data-search="{esc((str(product.get("vendor"))+' '+str(product.get("title"))+' '+tag_text).lower())}">
<a class="image-link" href="{esc(local_detail_url)}"><div class="image-wrap">{image_html}</div></a>
<button class="compact-head" type="button" aria-expanded="false">
<span class="vendor">{esc(product.get("vendor"))}</span><span class="title">{esc(product.get("title"))}</span>
<span class="compact-price">{esc(yen(price))}</span>{compare_html}
<span class="mini-row"><span class="status {status_class}">{status_text}</span><span class="stock-count">{in_count}/{len(variants)}</span></span>
</button>
<div class="detail"><div class="stock-box"><div class="stock-title">옵션별 재고</div>{build_variant_html(product)}</div>
<div class="date">updated: {updated or '-'}</div><div class="tags">{esc(tag_text)}</div><a class="button" href="{esc(local_detail_url)}">사진·설명 상세 보기</a>{product_button}</div>
</article>'''
        )
    generated_at = esc(payload.get("generated_at") or "-")
    refresh_seconds = settings.refresh_minutes * 60
    brand_json = json.dumps(dict(brand_counts), ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{refresh_seconds}"><title>{esc(settings.site_title)}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:Arial,"Noto Sans KR",sans-serif;background:#f5f5f3;color:#222}}header{{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.97);border-bottom:1px solid #ddd;padding:9px 8px;backdrop-filter:blur(8px)}}h1{{margin:0 0 7px;font-size:18px;text-align:center;letter-spacing:.02em}}.summary{{display:flex;gap:5px;overflow-x:auto;font-size:11px;color:#444;padding-bottom:3px}}.summary span{{background:#fff;border:1px solid #ddd;border-radius:999px;padding:4px 7px;white-space:nowrap}}.toolbar{{display:flex;gap:6px;align-items:center;justify-content:center;margin-top:8px;flex-wrap:wrap}}.search{{width:min(100%,330px);border:1px solid #ccc;background:#fff;border-radius:999px;padding:8px 12px;font-size:12px}}.brand-toggle,.filter-toggle{{border:1px solid #ccc;background:#fff;border-radius:999px;padding:7px 10px;font-weight:bold;cursor:pointer;font-size:12px}}.filter-toggle.active{{background:#167a2e;color:#fff;border-color:#167a2e}}.brand-panel{{display:none;margin:9px auto 0;background:#fff;border:1px solid #ddd;border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,.08);padding:9px;max-height:45vh;overflow:auto}}.brand-panel.open{{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}}.brand-button{{border:1px solid #ddd;background:#fafafa;border-radius:10px;padding:8px;text-align:left;cursor:pointer;font-weight:bold;color:#222;font-size:11px}}.brand-button span{{float:right;color:#777;font-weight:normal}}.brand-button.active{{background:#222;color:#fff;border-color:#222}}.brand-button.active span{{color:#ddd}}.current-filter{{text-align:center;margin-top:7px;font-size:12px;color:#333;font-weight:bold}}.notice{{font-size:10px;color:#777;text-align:center;padding:7px 10px 0;line-height:1.45}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;padding:7px}}.card{{background:#fff;border:1px solid #ddd;border-radius:10px;overflow:hidden;box-shadow:0 1px 5px rgba(0,0,0,.05)}}.card.hidden{{display:none}}.image-link{{display:block;text-decoration:none;color:inherit}}.image-wrap{{background:#eee;aspect-ratio:5/7;overflow:hidden}}img{{width:100%;height:100%;object-fit:cover;display:block}}.no-image{{display:grid;place-items:center;height:100%;font-size:10px;color:#888}}.compact-head{{width:100%;border:0;background:#fff;text-align:left;padding:6px;cursor:pointer}}.vendor{{display:block;color:#555;font-size:9px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.title{{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:29px;font-size:10.5px;line-height:1.35;font-weight:bold;margin-top:4px}}.compact-price{{display:block;font-size:13px;font-weight:800;margin-top:5px;color:#111;letter-spacing:-.02em}}.compact-compare{{display:block;font-size:10px;color:#777;text-decoration:line-through;margin-top:2px}}.mini-row{{display:flex;justify-content:space-between;align-items:center;gap:5px;margin-top:6px}}.status{{display:inline-block;padding:2px 5px;border-radius:999px;font-size:9px;font-weight:bold}}.available{{background:#e8f7e8;color:#167a2e}}.soldout{{background:#f7e8e8;color:#a82222}}.stock-count{{font-size:10px;font-weight:bold;background:#f0f0ee;border-radius:999px;padding:2px 5px;white-space:nowrap}}.detail{{display:none;padding:0 7px 8px;border-top:1px solid #eee}}.card.open .detail{{display:block}}.stock-box{{border:1px solid #e1e1df;background:#fafaf8;border-radius:9px;padding:7px;margin:8px 0}}.stock-title{{font-size:11px;font-weight:bold;margin-bottom:5px;color:#333}}.variant{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px;align-items:center;border-top:1px solid #e8e8e6;padding:6px 0;font-size:11px}}.variant:first-of-type{{border-top:0}}.variant-name{{line-height:1.3;overflow-wrap:anywhere}}.sku{{color:#888;font-size:9px;margin-top:2px}}.variant-right{{display:flex;flex-direction:column;align-items:flex-end;gap:3px}}.variant-price{{font-size:9px;color:#555}}.variant-status{{border-radius:999px;padding:3px 6px;font-weight:bold;white-space:nowrap;font-size:10px}}.in-stock .variant-status{{background:#dcf5dc;color:#137225}}.out-stock{{color:#999}}.out-stock .variant-status{{background:#eee;color:#777}}.empty-variant{{font-size:11px;color:#888}}.date{{color:#888;font-size:9px;margin:3px 0}}.tags{{color:#777;font-size:10px;line-height:1.35}}.button{{display:block;text-align:center;margin-top:9px;padding:8px;border-radius:8px;background:#222;color:#fff;text-decoration:none;font-size:12px}}.button.secondary{{background:#fff;color:#222;border:1px solid #bbb}}footer{{padding:18px 12px 26px;text-align:center;color:#777;font-size:10px;line-height:1.5}}@media(min-width:800px){{.grid{{grid-template-columns:repeat(5,1fr);max-width:1200px;margin:auto}}.brand-panel{{max-width:850px;grid-template-columns:repeat(4,1fr)}}}}@media(max-width:370px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
<header><h1>{esc(settings.site_title)}</h1><div class="summary"><span>총 {total_products}개</span><span>재고상품 {available_products}개</span><span>옵션 재고 {available_variants}/{total_variants}</span><span>{generated_at}</span><span>{settings.refresh_minutes}분 새로고침</span></div><div class="toolbar"><input id="search" class="search" type="search" placeholder="상품명·브랜드 검색"><button id="brandToggle" class="brand-toggle" type="button">브랜드 ▾</button><button id="availableToggle" class="filter-toggle" type="button">재고만 보기</button></div><div id="brandPanel" class="brand-panel">{''.join(brand_buttons)}</div><div id="currentFilter" class="current-filter">전체 브랜드 · {total_products}개</div></header>
<div class="notice">마지막 수집 시각 기준의 비공식 참고 페이지입니다. 실제 재고와 가격은 결제 시점에 달라질 수 있으며, 공식 상품 페이지는 로그인을 요구할 수 있습니다.</div>
<main id="grid" class="grid">{''.join(cards)}</main><footer>상품 이미지와 상표의 권리는 각 권리자에게 있습니다. 로그인 쿠키·비밀번호·개인정보는 이 페이지에 포함되지 않습니다.</footer>
<script>
const brandCounts={brand_json};let activeBrand='ALL',availableOnly=false;const cards=[...document.querySelectorAll('.card')];const search=document.getElementById('search');const panel=document.getElementById('brandPanel');const brandToggle=document.getElementById('brandToggle');const availableToggle=document.getElementById('availableToggle');const currentFilter=document.getElementById('currentFilter');
function applyFilters(){{const q=search.value.trim().toLowerCase();let visible=0;cards.forEach(card=>{{const brandOK=activeBrand==='ALL'||card.dataset.brand===activeBrand;const stockOK=!availableOnly||card.dataset.available==='true';const searchOK=!q||card.dataset.search.includes(q);const show=brandOK&&stockOK&&searchOK;card.classList.toggle('hidden',!show);if(show)visible++;}});currentFilter.textContent=(activeBrand==='ALL'?'전체 브랜드':activeBrand)+' · '+visible+'개';}}
brandToggle.addEventListener('click',()=>panel.classList.toggle('open'));availableToggle.addEventListener('click',()=>{{availableOnly=!availableOnly;availableToggle.classList.toggle('active',availableOnly);applyFilters();}});search.addEventListener('input',applyFilters);document.querySelectorAll('.brand-button').forEach(btn=>btn.addEventListener('click',()=>{{activeBrand=btn.dataset.brand;document.querySelectorAll('.brand-button').forEach(b=>b.classList.toggle('active',b===btn));panel.classList.remove('open');applyFilters();}}));document.querySelectorAll('.compact-head').forEach(btn=>btn.addEventListener('click',()=>{{const card=btn.closest('.card');card.classList.toggle('open');btn.setAttribute('aria-expanded',card.classList.contains('open'));}}));
</script></body></html>'''


async def collect(settings: Settings, *, headless: bool | None = None) -> dict[str, Any]:
    ensure_dirs()
    actual_headless = settings.headless_collect if headless is None else headless
    async with async_playwright() as playwright:
        context = await launch_context(playwright, settings, headless=actual_headless)
        page = await get_page(context)
        try:
            log("SPECIAL PRICE 페이지 접속")
            await goto_collection(page, settings)
            text = await body_text(page)
            login_message = next((msg for msg in LOGIN_REQUIRED_TEXTS if msg.lower() in text.lower()), None)
            if login_message:
                await save_debug(page, {"reason": "login_required"})
                raise CatalogError(
                    "로그인 상태가 확인되지 않았습니다. 02_LOGIN.bat을 다시 실행한 뒤 로그인하고 저장하세요."
                )
            products = await fetch_collection_products(page, settings)
            method = "authenticated_products_json"
            if not products:
                links = await extract_product_links(page, settings)
                if not links:
                    await save_debug(page, {"reason": "no_products_or_links"})
                    raise CatalogError(
                        "상품 API와 상품 링크를 모두 찾지 못했습니다. 07_DIAGNOSE.bat을 실행한 뒤 private 폴더의 디버그 파일을 확인하세요."
                    )
                products = await fetch_products_from_links(page, links, settings)
                method = "dom_links_and_product_json"
            normalized = [normalize_product(item, settings) for item in products]
            normalized = [p for p in normalized if p.get("handle") or p.get("title")]
            normalized = await enrich_product_details(page, normalized, settings)
            if not normalized:
                await save_debug(page, {"reason": "normalization_empty", "raw_count": len(products)})
                raise CatalogError("수집 데이터는 있었지만 상품으로 변환하지 못했습니다.")
            payload = {
                "generated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST"),
                "source": settings.collection_url,
                "collection_method": method,
                "product_count": len(normalized),
                "products": normalized,
            }
            CATALOG_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            INDEX_HTML.write_text(build_dashboard(payload, settings), encoding="utf-8")
            log(f"완료: 상품 {len(normalized)}개, index.html 생성")
            return payload
        except Exception:
            try:
                await save_debug(page, {"command": "collect"})
            except Exception:
                pass
            raise
        finally:
            await context.close()


async def login(settings: Settings) -> None:
    ensure_dirs()
    async with async_playwright() as playwright:
        context = await launch_context(playwright, settings, headless=False)
        page = await get_page(context)
        try:
            await goto_collection(page, settings)
            print("\n브라우저에서 직접 로그인하세요.")
            print("SPECIAL PRICE 상품 목록과 사진이 보이면 이 창으로 돌아와 Enter를 누르세요.\n")
            await asyncio.to_thread(input, "로그인 완료 후 Enter: ")
            await goto_collection(page, settings)
            products = await fetch_collection_products(page, settings)
            text = await body_text(page)
            if not any(msg.lower() in text.lower() for msg in LOGIN_REQUIRED_TEXTS):
                log("로그인 프로필 저장 완료")
            else:
                await save_debug(page, {"reason": "login_verify_failed"})
                raise CatalogError("로그인이 확인되지 않았습니다. 상품 목록이 보이는 상태에서 다시 실행하세요.")
        finally:
            await context.close()


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
    )


def publish(settings: Settings) -> bool:
    if not (ROOT / ".git").exists():
        raise CatalogError("Git 저장소가 연결되지 않았습니다. 먼저 04_CONNECT_GITHUB.bat을 실행하세요.")
    remote = run_git(["remote", "get-url", "origin"], check=False)
    if remote.returncode != 0:
        raise CatalogError("GitHub origin 주소가 없습니다. 04_CONNECT_GITHUB.bat을 다시 실행하세요.")
    run_git(["add", "index.html", "detail.html", "data/catalog.json"])
    status = run_git(["status", "--porcelain", "--", "index.html", "detail.html", "data/catalog.json"])
    if not status.stdout.strip():
        log("GitHub에 올릴 변경 없음")
        return False
    message = "Update SPECIAL PRICE catalog " + datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    commit = run_git(["commit", "-m", message], check=False)
    if commit.returncode != 0:
        raise CatalogError(f"git commit 실패:\n{commit.stdout}\n{commit.stderr}")
    pushed = run_git(["push", "origin", settings.git_branch], check=False)
    if pushed.returncode != 0:
        raise CatalogError(f"git push 실패:\n{pushed.stdout}\n{pushed.stderr}")
    log("GitHub 업로드 완료")
    return True


async def monitor(settings: Settings, do_publish: bool) -> None:
    interval = max(60, settings.refresh_minutes * 60)
    log(f"자동 갱신 시작: {settings.refresh_minutes}분 간격")
    log("종료하려면 이 창에서 Ctrl+C를 누르세요.")
    while True:
        started = time.monotonic()
        try:
            await collect(settings)
            if do_publish:
                publish(settings)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log(f"업데이트 실패: {type(exc).__name__}: {exc}")
            log("마지막 정상 index.html은 유지됩니다.")
        elapsed = time.monotonic() - started
        sleep_for = max(5, interval - elapsed)
        log(f"다음 확인까지 약 {int(sleep_for)}초")
        await asyncio.sleep(sleep_for)


async def diagnose(settings: Settings) -> None:
    try:
        await collect(settings, headless=False)
        log("진단 수집 성공")
    except Exception as exc:
        log(f"진단 수집 실패: {exc}")
        log(f"디버그 파일: {DEBUG_HTML}")
        log(f"스크린샷: {DEBUG_SCREENSHOT}")
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ISSEY MIYAKE SPECIAL PRICE catalog collector")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="직접 로그인하고 브라우저 프로필 저장")
    collect_parser = sub.add_parser("collect", help="한 번 수집")
    collect_parser.add_argument("--publish", action="store_true")
    monitor_parser = sub.add_parser("monitor", help="주기적으로 수집")
    monitor_parser.add_argument("--publish", action="store_true")
    sub.add_parser("publish", help="현재 index.html만 GitHub에 업로드")
    sub.add_parser("diagnose", help="브라우저를 보이게 열고 진단")
    return parser.parse_args()


def main() -> int:
    os.chdir(ROOT)
    settings = load_settings()
    args = parse_args()
    try:
        if args.command == "login":
            asyncio.run(login(settings))
        elif args.command == "collect":
            asyncio.run(collect(settings))
            if args.publish:
                publish(settings)
        elif args.command == "monitor":
            asyncio.run(monitor(settings, args.publish))
        elif args.command == "publish":
            publish(settings)
        elif args.command == "diagnose":
            asyncio.run(diagnose(settings))
        return 0
    except KeyboardInterrupt:
        log("사용자가 종료했습니다.")
        return 0
    except CatalogError as exc:
        log(f"오류: {exc}")
        return 2
    except Exception as exc:
        log(f"예상하지 못한 오류: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
