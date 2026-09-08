import {describe, expect, it} from 'vitest';
import {layout} from './metadata';
import type {EditList, MediaFacts} from './metadata';

const facts = (
	durationInSeconds: number,
	fps = 24,
	width = 1280,
	height = 720,
): MediaFacts => ({durationInSeconds, fps, width, height});

const baseList: EditList = {
	episode: 'ep01',
	format: '16x9',
	segments: [
		{n: 1, file: 'segments/001.mp4'},
		{n: 2, file: 'segments/002.mp4'},
	],
	voice: [],
	sfx: [],
	music: [],
	duck: {gain: 0.4842, attackMs: 5, releaseMs: 1050},
	expected: {segments: 2, segmentSeconds: 5, tolerance: 0.05},
	shorts: {banner: 'Маяк', background: '#101820', accent: '#E8B04B'},
};

const baseMedia: Record<string, MediaFacts> = {
	'segments/001.mp4': facts(5.0),
	'segments/002.mp4': facts(5.0),
};

describe('layout: геометрия и время', () => {
	it('берёт fps, ширину и высоту из первого отрезка', () => {
		const l = layout(baseList, baseMedia);
		expect(l.fps).toBe(24);
		expect(l.width).toBe(1280);
		expect(l.height).toBe(720);
	});

	it('ставит отрезки встык и считает общую длительность в кадрах', () => {
		const l = layout(baseList, baseMedia);
		expect(l.segments).toEqual([
			{n: 1, file: 'segments/001.mp4', from: 0, durationInFrames: 120},
			{n: 2, file: 'segments/002.mp4', from: 120, durationInFrames: 120},
		]);
		expect(l.durationInFrames).toBe(240);
	});

	it('суммирует кадры отрезков, а не округляет сумму секунд', () => {
		// 4.074 c при 24 fps = 97.78 кадра -> 98 у каждого; сумма 196.
		// Округление суммы (8.148 c -> 196) совпадает здесь, но при трёх отрезках
		// разошлось бы: важно, что стыки не «уплывают» друг относительно друга.
		const l = layout(baseList, {
			'segments/001.mp4': facts(4.074),
			'segments/002.mp4': facts(4.074),
		});
		expect(l.segments[1].from).toBe(98);
		expect(l.durationInFrames).toBe(196);
	});
});

describe('layout: звук', () => {
	const withAudio: EditList = {
		...baseList,
		voice: [
			{
				id: 'v1',
				file: 'audio/v1.mp3',
				segment: 2,
				offset: 1.5,
				volume: 1,
				text: 'Свет погас.',
			},
		],
		music: [
			{id: 'm1', file: 'audio/m1.mp3', segment: 1, offset: 0, volume: 0.35},
		],
	};
	const media = {
		...baseMedia,
		'audio/v1.mp3': facts(2),
		'audio/m1.mp3': facts(10),
	};

	it('переводит segment+offset в абсолютный кадр', () => {
		const l = layout(withAudio, media);
		// отрезок 2 начинается на 5.0 c = кадр 120; смещение 1.5 c = 36 кадров.
		expect(l.voice[0].from).toBe(156);
		expect(l.voice[0].durationInFrames).toBe(48);
		expect(l.voice[0].text).toBe('Свет погас.');
		expect(l.music[0].from).toBe(0);
	});

	it('предупреждает, когда реплика вылезает за границу своего отрезка', () => {
		const l = layout(withAudio, {...media, 'audio/v1.mp3': facts(4)});
		expect(l.warnings.join(' ')).toContain('v1');
		expect(l.errors).toEqual([]);
	});

	it('молчит, когда реплика умещается', () => {
		expect(layout(withAudio, media).warnings).toEqual([]);
	});

	it('не ругается на музыку, растянутую за пределы своего отрезка', () => {
		// Подложка ставится на первый отрезок и играет весь эпизод — это штатный
		// случай, а не ошибка. Прежний mix_audio.py предупреждал и здесь, то есть
		// ругался на нормальную работу.
		const l = layout(withAudio, {...media, 'audio/m1.mp3': facts(10)});
		expect(l.music[0].durationInFrames).toBe(240);
		expect(l.warnings).toEqual([]);
	});
});

describe('layout: расхождения между отрезками', () => {
	it('расхождение fps — предупреждение, рендер продолжается', () => {
		const l = layout(baseList, {
			'segments/001.mp4': facts(5, 24),
			'segments/002.mp4': facts(5, 30),
		});
		expect(l.warnings.join(' ')).toContain('fps');
		expect(l.errors).toEqual([]);
		expect(l.fps).toBe(24);
	});

	it('расхождение размеров — отказ со списком файлов и разрешений', () => {
		const l = layout(baseList, {
			'segments/001.mp4': facts(5, 24, 1280, 720),
			'segments/002.mp4': facts(5, 24, 1284, 716),
		});
		expect(l.errors.join(' ')).toContain('1284x716');
		expect(l.errors.join(' ')).toContain('segments/002.mp4');
	});
});

describe('layout: контроль длительности', () => {
	it('молчит внутри допуска ±5%', () => {
		expect(layout(baseList, baseMedia).warnings).toEqual([]);
	});

	it('предупреждает при выходе за допуск', () => {
		const l = layout(baseList, {
			'segments/001.mp4': facts(5),
			'segments/002.mp4': facts(9),
		});
		expect(l.warnings.join(' ')).toContain('±5%');
	});
});

describe('layout: отсутствующие факты', () => {
	it('файл без метаданных — отказ, а не тихий ноль', () => {
		const l = layout(baseList, {'segments/001.mp4': facts(5)});
		expect(l.errors.join(' ')).toContain('segments/002.mp4');
	});
});

describe('огибающая и фоли (дизайн 2026-09-04)', () => {
	const media = {...baseMedia, 'audio/s1.mp3': facts(3.0),
		'audio/f1.mp4': facts(5.0)};

	it('огибающая доезжает из листа в раскладку', () => {
		const l = layout({...baseList, sfx: [{id: 's1', file: 'audio/s1.mp3',
			segment: 1, offset: 0, volume: 0.7,
			envelope: [[0, 0.1], [3, 1]]}]}, media);
		expect(l.sfx[0].envelope).toEqual([[0, 0.1], [3, 1]]);
	});

	it('единица без огибающей её не получает', () => {
		const l = layout({...baseList, sfx: [{id: 's1', file: 'audio/s1.mp3',
			segment: 1, offset: 0, volume: 0.7}]}, media);
		expect(l.sfx[0].envelope).toBeUndefined();
	});

	it('фоли встаёт на свой отрезок', () => {
		const l = layout({...baseList, foley: [{id: 'f1', file: 'audio/f1.mp4',
			segment: 2, offset: 0, volume: 0.5}]}, media);
		expect(l.foley[0].from).toBe(120);
	});

	it('лист без списка foley даёт пустой список, а не падение', () => {
		// старые монтажные листы обязаны продолжать собираться
		expect(layout(baseList, baseMedia).foley).toEqual([]);
	});
});

describe('подложка отдельным слоем (правки 2026-09-05)', () => {
	it('лист без ambience даёт пустой список, а не падение', () => {
		expect(layout(baseList, baseMedia).ambience).toEqual([]);
	});

	it('подложка размещается как остальные дорожки', () => {
		const media = {...baseMedia, 'audio/amb.mp3': facts(10.0)};
		const l = layout({...baseList, ambience: [{id: 'a1', file: 'audio/amb.mp3',
			segment: 1, offset: 0, volume: 0.16}]}, media);
		expect(l.ambience[0].from).toBe(0);
		expect(l.ambience[0].volume).toBe(0.16);
	});
});

describe('перечень звуковых файлов', () => {
	it('покрывает все слои, а не только три первых', async () => {
		// Слой, забытый в audioFiles, получает нулевую длительность и роняет
		// рендер целиком: "durationInFrames must be positive".
		const src = await import('node:fs/promises').then((fs) =>
			fs.readFile(new URL('./episodeMetadata.ts', import.meta.url), 'utf-8'),
		);
		const block = src.slice(src.indexOf('const audioFiles'),
			src.indexOf('const readFacts'));
		for (const layer of ['voice', 'sfx', 'music', 'ambience', 'foley']) {
			expect(block).toContain(`props.${layer}`);
		}
	});
});

describe('режим кадров', () => {
	const list = {
		episode: 'ep01',
		format: '16x9' as const,
		mode: 'stills' as const,
		segments: [],
		stills: [
			{n: 1, file: '001.png'},
			{n: 2, file: '002.png'},
		],
		stillsSettings: {minSeconds: 3, tailSeconds: 0.6, crossfadeSeconds: 0.4, zoom: 1.08},
		voice: [
			{id: 'v2', file: 'v2.mp3', segment: 2, offset: 0.5, volume: 1},
		],
		sfx: [],
		music: [],
		ambience: [],
		foley: [],
		duck: {gain: 1, attackMs: 120, releaseMs: 700},
		expected: {segments: 0, segmentSeconds: 5, tolerance: 0.05},
		shorts: {background: '#101820', accent: '#E8B04B', banner: '', caption: ''},
	};
	const media = {
		'001.png': {durationInSeconds: 0, fps: 30, width: 1280, height: 720},
		'002.png': {durationInSeconds: 0, fps: 30, width: 1280, height: 720},
		'v2.mp3': {durationInSeconds: 4, fps: 0, width: 0, height: 0},
	};

	it('реплика встаёт в свой кадр, а не в начало эпизода', () => {
		const placed = layout(list, media);
		const first = placed.stills[0];
		// Реплика привязана ко ВТОРОМУ кадру: её старт не может быть раньше,
		// чем закончился первый.
		expect(placed.voice[0].from).toBeGreaterThanOrEqual(first.durationInFrames);
	});

	it('длительность эпизода — сумма кадров, а не нулей', () => {
		const placed = layout(list, media);
		expect(placed.durationInFrames).toBe(
			placed.stills.reduce((t, s) => t + s.durationInFrames, 0),
		);
		expect(placed.durationInFrames).toBeGreaterThan(0);
	});

	it('размер берётся у кадра: опорного видео в этом режиме нет', () => {
		const placed = layout(list, media);
		expect(placed.width).toBe(1280);
		expect(placed.height).toBe(720);
	});
});
