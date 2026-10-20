"""Log in to Snowflake with credentials supplied at runtime."""

import os
import re
from getpass import getpass

from camoufox.sync_api import Camoufox
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def required_value(
    environment_name: str, prompt: str, *, secret: bool = False
) -> str:
    value = os.environ.get(environment_name)
    if value:
        return value
    value = getpass(prompt) if secret else input(prompt)
    if not value:
        raise ValueError(f"{environment_name} cannot be empty")
    return value


def main() -> None:
    account = required_value("SNOWFLAKE_ACCOUNT", "Account identifier: ", secret=True)
    username = required_value("SNOWFLAKE_USERNAME", "Username: ", secret=True)
    password = required_value("SNOWFLAKE_PASSWORD", "Password: ", secret=True)

    with Camoufox(
        headless=False,
        os="macos",
        locale="zh-CN",
        fingerprint_preset=True,
        humanize=True,
    ) as browser:
        page = browser.new_page(no_viewport=True)
        page.goto("https://app.snowflake.com/", wait_until="domcontentloaded")

        account_input = page.get_by_placeholder("Account identifier")
        account_input.fill(account)
        account_input.press("Enter")

        page.wait_for_url(
            re.compile(r"https://[^/]+\.snowflakecomputing\.com/oauth/authorize"),
            timeout=60_000,
        )
        password_input = page.locator('input[type="password"]')
        password_input.wait_for(state="visible", timeout=60_000)

        page.locator('input[type="text"]').fill(username)
        password_input.fill(password)
        page.get_by_text("Sign in", exact=True).click()

        try:
            page.wait_for_url(
                re.compile(r"https://app\.snowflake\.com(?:/|$)"),
                timeout=120_000,
            )
            print("Snowflake 登录成功。")
        except PlaywrightTimeoutError:
            print("登录尚未完成；请在浏览器中处理验证码、MFA 或错误提示。")

        input("按回车键关闭浏览器……")


if __name__ == "__main__":
    main()
