/**
 * How long each exit-IP probe may take. Twin of the timeout tests in
 * python/tests/test_proxy_geo.py: publicIP() polls its URL list through a
 * proxy with the short PROXIED_IP_LIST_TIMEOUT_MS, the single ip-api lookup in
 * proxyExitGeo() keeps PROXIED_IP_TIMEOUT_MS, and direct probes keep
 * DIRECT_IP_TIMEOUT_MS.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const impit = vi.hoisted(() => ({
	// The timeout each request ran under: its own, else its client's.
	requests: [] as { url: string; proxy?: string; timeout?: number }[],
	fail: true,
}));

vi.mock("impit", () => ({
	Impit: class {
		constructor(private options: { proxyUrl?: string; timeout?: number }) {}
		async fetch(url: string, init?: { timeout?: number }) {
			impit.requests.push({
				url,
				proxy: this.options.proxyUrl,
				timeout: init?.timeout ?? this.options.timeout,
			});
			if (impit.fail) {
				throw new Error("timed out");
			}
			return {
				ok: true,
				status: 200,
				text: async () => "203.0.113.7",
				json: async () => ({
					status: "success",
					query: "203.0.113.7",
					timezone: "Europe/Paris",
				}),
			};
		}
	},
}));

const ip = await import("../src/ip.js");

beforeEach(() => {
	impit.requests.length = 0;
	impit.fail = true;
});

describe("exit-IP lookup timeouts", () => {
	it("the proxied list timeout is shorter than the single proxied lookup", () => {
		expect(ip.PROXIED_IP_LIST_TIMEOUT_MS).toBe(6000);
		expect(ip.PROXIED_IP_TIMEOUT_MS).toBe(15000);
		expect(ip.DIRECT_IP_TIMEOUT_MS).toBe(5000);
	});

	it("a dead proxy polls the IP list with the short timeout", async () => {
		const proxy = "http://dead.example:8080";
		await expect(ip.publicIP(proxy)).rejects.toThrow();
		expect(impit.requests.length).toBeGreaterThan(1);
		for (const request of impit.requests) {
			expect(request.proxy).toBe(proxy);
			expect(request.timeout).toBe(ip.PROXIED_IP_LIST_TIMEOUT_MS);
		}
	});

	it("direct lookups keep the direct timeout", async () => {
		await expect(ip.publicIP()).rejects.toThrow();
		expect(impit.requests.length).toBeGreaterThan(1);
		for (const request of impit.requests) {
			expect(request.proxy).toBeUndefined();
			expect(request.timeout).toBe(ip.DIRECT_IP_TIMEOUT_MS);
		}
	});

	it("the ip-api lookup through a proxy keeps the longer timeout", async () => {
		impit.fail = false;
		const proxy = "http://slow.example:8080";
		expect(await ip.proxyExitGeo(proxy)).toEqual([
			"203.0.113.7",
			"Europe/Paris",
		]);
		expect(impit.requests).toEqual([
			{
				url: "http://ip-api.com/json?fields=status,message,query,timezone",
				proxy,
				timeout: ip.PROXIED_IP_TIMEOUT_MS,
			},
		]);
	});
});
