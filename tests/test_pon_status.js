'use strict';
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');

const source = readFileSync(join(__dirname,
	'../package/pon/userspace/luci-app-pon/htdocs/luci-static/resources/view/pon/status.js'), 'utf8');
const acl = JSON.parse(readFileSync(join(__dirname,
	'../package/pon/userspace/luci-app-pon/root/usr/share/rpcd/acl.d/luci-app-pon.json'), 'utf8'))['luci-app-pon'];
const sections = {
	xpon: [{ '.name': 'line0', device: 'pon0', mode: 'xgspon' }],
	omci: [{ '.name': 'line0_omci', line: 'line0', device: 'omci0' }],
	oam: [{ '.name': 'line0_oam', line: 'line0', device: 'oam0' }]
};
const ok = value => ({ code: 0, stdout: JSON.stringify(value), stderr: '' });

function load(exec, config = sections) {
	const view = new Function('fs', 'uci', 'view', '_', source)(
		{ exec }, { load: () => Promise.resolve(), sections: (_, type) => config[type] || [] },
		{ extend: value => value }, value => value);
	return view.load();
}

test('shows missing xpon binding and daemon socket errors instead of invalid JSON', async () => {
	const data = await load(async command => ({ code: 1, stdout: '', stderr: command.endsWith('/ponctl')
		? "PON device 'pon0' was not found or has no xpon binding\n"
		: 'No such file or directory (os error 2)\n' }));
	assert.match(data.lines[0].error, /no xpon binding$/);
	assert.match(data.omci[0].error, /No such file or directory/);
	assert.equal(data.oam.length, 0);
});

test('does not accept stdout JSON from an unsuccessful command', async () => {
	const data = await load(async () => ({ ...ok({ schema_version: 1, line: {} }), code: 1, stderr: 'probe failed' }));
	assert.equal(data.lines[0].error, 'probe failed');
	assert.equal(data.omci[0].error, 'probe failed');
});

test('preserves RPC errors per instance and keeps other status results', async () => {
	const data = await load(async command => {
		if (command.endsWith('/ponctl')) throw new Error('Permission denied');
		return ok({ rx_messages: 12 });
	});
	assert.equal(data.lines[0].error, 'Device unavailable: Permission denied');
	assert.equal(data.omci[0].error, null);
	assert.equal(data.omci[0].values.rx_messages, 12);
});

test('validates line schema and protocol object shape', async () => {
	for (const value of [null, [], 'text', 1]) {
		const data = await load(async () => ok(value));
		assert.equal(data.lines[0].error, 'Invalid status response');
		assert.equal(data.omci[0].error, 'Invalid OMCI status response');
	}
	for (const value of [{ schema_version: 2, line: {} }, { schema_version: 1, line: [] },
		{ schema_version: 1, line: null }]) {
		const data = await load(async () => ok(value));
		assert.equal(data.lines[0].error, 'Invalid status response');
	}
	const data = await load(async () => ({ code: 0, stdout: '', stderr: '' }));
	assert.equal(data.lines[0].error, 'Invalid status response');
});

test('retains status fields and selects OAM for an EPON line', async () => {
	const calls = [];
	const data = await load(async (command, args) => {
		calls.push([command, args]);
		return command.endsWith('/ponctl') ? ok({ schema_version: 1,
			line: { active_mode: 'epon-1g' }, frontend: { rx_power_dbm: -19.5 }, counters: { rx: 10 } })
			: ok({ rx_messages: 8 });
	}, { ...sections, xpon: [{ ...sections.xpon[0], mode: 'epon-1g' }] });
	assert.equal(data.lines[0].error, null);
	assert.equal(data.lines[0].frontend.rx_power_dbm, -19.5);
	assert.equal(data.lines[0].counters.rx, 10);
	assert.equal(data.omci.length, 0);
	assert.equal(data.oam[0].values.rx_messages, 8);
	assert.deepEqual(calls, [
		['/usr/sbin/ponctl', ['--device', 'pon0', 'status', '--json']],
		['/usr/bin/pondctl', ['status', '--line', 'line0']]
	]);
});

test('read-only sessions can execute only the existing allowlisted status commands', () => {
	assert.ok(acl.read.ubus.file.includes('exec'));
	assert.deepEqual(acl.read.file['/usr/sbin/ponctl --device * status --json'], ['exec']);
	assert.deepEqual(acl.read.file['/usr/bin/pondctl status --line *'], ['exec']);
	assert.equal(acl.read.file['/bin/sh'], undefined);
	assert.equal(acl.read.file['*'], undefined);
	assert.equal(acl.read.file['/usr/libexec/pon-board-identity write *'], undefined);
});
