"""Open Google in Camoufox and search for ChatGPT."""

from camoufox.sync_api import Camoufox


def main() -> None:
    with Camoufox(
        headless=False,
        os="macos",
        locale="zh-CN",
        fingerprint_preset=True,
        humanize=True,
    ) as browser:
        page = browser.new_page(no_viewport=True)
        page.goto("https://www.google.com/", wait_until="domcontentloaded")

        search_box = page.locator('textarea[name="q"], input[name="q"]')
        search_box.fill("ChatGPT")
        search_box.press("Enter")
        page.wait_for_url("**/search?**")

        print(f"已打开搜索结果：{page.title()}")
        input("按回车键关闭浏览器……")


if __name__ == "__main__":
    main()
