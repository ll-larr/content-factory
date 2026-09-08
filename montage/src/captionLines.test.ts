import {describe, expect, it} from 'vitest';
import {MAX_LINE, splitCaption, visibleLine} from './captionLines';

describe('splitCaption', () => {
	it('короткую реплику оставляет одной строкой', () => {
		expect(splitCaption('Свет погас.')).toEqual(['Свет погас.']);
	});

	it('режет по знакам препинания, а не посреди слова', () => {
		const lines = splitCaption(
			'Свет погас, и тогда она поняла, что маяк придётся собрать заново.',
		);
		expect(lines.length).toBeGreaterThan(1);
		for (const line of lines) {
			expect(line.length).toBeLessThanOrEqual(MAX_LINE);
		}
		expect(lines.join(' ')).toBe(
			'Свет погас, и тогда она поняла, что маяк придётся собрать заново.',
		);
	});

	it('длинную фразу без пунктуации режет по пробелам', () => {
		const text = 'слово '.repeat(20).trim();
		const lines = splitCaption(text);
		for (const line of lines) {
			expect(line.length).toBeLessThanOrEqual(MAX_LINE);
		}
		expect(lines.join(' ')).toBe(text);
	});

	it('слово длиннее строки не теряется', () => {
		const long = 'а'.repeat(MAX_LINE + 10);
		expect(splitCaption(long).join('')).toContain(long);
	});

	it('пустой текст даёт пустой список', () => {
		expect(splitCaption('   ')).toEqual([]);
	});
});

describe('visibleLine', () => {
	const lines = ['первая', 'вторая', 'третья'];

	it('делит интервал реплики поровну между строками', () => {
		expect(visibleLine(lines, 0, 30)).toBe('первая');
		expect(visibleLine(lines, 10, 30)).toBe('вторая');
		expect(visibleLine(lines, 25, 30)).toBe('третья');
	});

	it('на последнем кадре показывает последнюю строку, а не выходит за список', () => {
		expect(visibleLine(lines, 29, 30)).toBe('третья');
		expect(visibleLine(lines, 30, 30)).toBe('третья');
	});

	it('без строк возвращает пустоту', () => {
		expect(visibleLine([], 5, 30)).toBe('');
	});
});
