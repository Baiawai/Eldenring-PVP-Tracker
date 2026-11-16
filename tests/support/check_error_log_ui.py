"""Exercise error-log links in both panels using the isolated browser server."""
import check_online_profile_notice as harness


def check(browser, url):
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    payload = {'request': 'success', 'environment': {'tracker': 'test', 'python': 'test', 'os': 'test', 'data_path': 'C:/data'},
               'storage': {'databases': [], 'database_bytes': 0, 'disk_free_bytes': 0},
               'error_log': {'path': 'C:/data/tracker-errors.log', 'exists': True}}
    context.route('**/system-details', lambda route: route.fulfill(json=payload))
    calls = []
    def open_log(route):
        calls.append(route.request.method)
        route.fulfill(json={'opened': True})
    context.route('**/error-log/open', open_log)
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until='load')
        page.locator('#menu_button_information').click()
        first = page.locator('#information_panel [data-error-log-open]')
        first.wait_for(state='visible')
        page.wait_for_function("() => document.querySelector('#information_panel [data-error-log-open]').textContent.includes('tracker-errors.log')")
        assert first.is_enabled()
        assert first.evaluate("e => getComputedStyle(e).backgroundImage") == 'none'
        for language in harness.LANGUAGES:
            page.evaluate('(code) => launchLanguages(code)', language)
            expected = page.evaluate("code => code === 'fra' ? 'Journal des erreurs' : ELDEN_UI_PACKS[code].modern.error_log_label", language)
            assert page.locator('#information_panel .error-log-row > span').inner_text() == expected
        first.click()
        page.wait_for_timeout(100)
        assert calls == ['POST'], calls
        page.locator('#menu_button_settings').click()
        page.locator('.btn_menu_settings[menu="6"]').click()
        second = page.locator('.diagnostics-settings [data-error-log-open]')
        second.wait_for(state='visible')
        assert second.is_enabled() and 'tracker-errors.log' in second.inner_text()
        second.click()
        page.wait_for_timeout(100)
        assert calls == ['POST', 'POST'], calls
        payload['error_log']['exists'] = False
        page.locator('.btn_menu_settings[menu="6"]').click()
        page.wait_for_function("() => document.querySelector('.diagnostics-settings [data-error-log-open]').disabled")
        assert page.locator('.diagnostics-settings [data-error-log-status]').inner_text()
        assert not errors, errors
    finally:
        context.close()


if __name__ == '__main__':
    harness.check = check
    harness.main()
    print("Error-log links passed in both panels and all languages.")
