const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");


const source = fs.readFileSync(
    path.join(__dirname, "../static/telemetry/embed.js"),
    "utf8"
);
const embeddedId = "d8755a51-1984-451b-9bd1-8a5f220ed205";


function makeResponse(dashboards, token = "first-token") {
    return {
        status: 200,
        ok: true,
        async json() {
            return {
                superset_url: "http://localhost:8088",
                dashboards,
                guest_token: token,
            };
        },
    };
}


async function runPage(responses, search = "") {
    const options = [];
    const container = {
        dataset: { embedEndpoint: "/api/telemetry/embed" },
        cleared: false,
        replaceChildren() {
            this.cleared = true;
        },
    };
    const status = { textContent: "Загрузка" };
    const picker = { hidden: true };
    const selector = {
        value: "",
        replaceChildren() {
            options.length = 0;
        },
        append(option) {
            options.push(option);
        },
        addEventListener(event, callback) {
            this.onChange = callback;
        },
    };
    const elements = {
        "dashboard-container": container,
        "dashboard-status": status,
        "dashboard-picker": picker,
        "dashboard-select": selector,
    };
    const location = {
        search,
        href: "http://localhost:8000/telemetry/" + search,
        assign(value) {
            this.assigned = value;
        },
    };
    let embedded;
    let requestCount = 0;
    const context = {
        URL,
        URLSearchParams,
        location,
        document: {
            getElementById(id) {
                return elements[id];
            },
            querySelector() {
                return { value: "csrf-token" };
            },
            createElement() {
                return { value: "", textContent: "" };
            },
        },
        async fetch(url, options) {
            assert.equal(url, "/api/telemetry/embed");
            assert.equal(options.method, "POST");
            assert.equal(options.headers["X-CSRFToken"], "csrf-token");
            assert.equal(options.credentials, "same-origin");
            requestCount += 1;
            return responses.shift();
        },
        supersetEmbeddedSdk: {
            async embedDashboard(options) {
                embedded = options;
                await options.fetchGuestToken();
            },
        },
    };
    vm.runInNewContext(source, context);
    await new Promise(setImmediate);
    return {
        container,
        status,
        picker,
        selector,
        options,
        location,
        embedded: () => embedded,
        requestCount: () => requestCount,
    };
}


test("разрешённый UUID и обновление токена новым POST", async () => {
    const dashboards = [{
        code: "overview", title: "Company Overview", embedded_id: embeddedId,
    }];
    const page = await runPage([
        makeResponse(dashboards),
        makeResponse(dashboards, "renewed-token"),
    ], "?dashboard=arbitrary-uuid");

    assert.equal(page.embedded().id, embeddedId);
    assert.equal(page.embedded().supersetDomain, "http://localhost:8088");
    assert.equal(
        page.embedded().referrerPolicy,
        "strict-origin-when-cross-origin"
    );
    assert.equal(page.requestCount(), 1);
    assert.equal(await page.embedded().fetchGuestToken(), "renewed-token");
    assert.equal(page.requestCount(), 2);
});


test("запрет доступа при обновлении закрывает iframe", async () => {
    const dashboards = [{
        code: "overview", title: "Company Overview", embedded_id: embeddedId,
    }];
    const page = await runPage([
        makeResponse(dashboards),
        { status: 401, ok: false },
    ]);

    await assert.rejects(page.embedded().fetchGuestToken());
    assert.equal(page.container.cleared, true);
    assert.match(page.status.textContent, /Сессия завершилась/);
});


test("выбор нескольких дашбордов использует только список сервера", async () => {
    const dashboards = [
        { code: "overview", title: "Обзор", embedded_id: embeddedId },
        {
            code: "director",
            title: "Директор",
            embedded_id: "68a5f203-7751-4223-a2b2-c2be403c4df1",
        },
    ];
    const page = await runPage([makeResponse(dashboards)]);

    assert.equal(page.picker.hidden, false);
    assert.equal(page.options.length, 2);
    page.selector.value = "director";
    page.selector.onChange();
    assert.match(page.location.assigned, /dashboard=director/);
});
