/**
 * Раскладка монтажного листа в кадры (спека 2026-08-31 §4).
 *
 * Python отдаёт намерение — какие файлы, в каком порядке, с каким смещением
 * внутри отрезка. Здесь оно превращается в абсолютные кадры по фактам о медиа,
 * которые читает `parseMedia`. Сама функция чистая: `media` приходит словарём,
 * поэтому тесты не трогают ни одного файла.
 */

export type MediaFacts = {
	durationInSeconds: number;
	fps: number;
	width: number;
	height: number;
};

import type {EnvelopePoint} from './envelope';
import {placeStills, stillsDuration} from './stills';
import type {ListStill, PlacedStill, StillsSettings} from './stills';

export type ListSegment = {n: number; file: string};

export type ListAudio = {
	id: string;
	file: string;
	segment: number;
	offset: number;
	volume: number;
	text?: string;
	/** Движение уровня внутри единицы: приближение, отдаление, затухание. */
	envelope?: EnvelopePoint[];
};

export type EditList = {
	episode: string;
	format: '16x9' | '9x16';
	/** Режим сборки. Старые листы без поля читаются как 'video'. */
	mode?: 'video' | 'stills';
	segments: ListSegment[];
	stills?: ListStill[];
	stillsSettings?: StillsSettings;
	voice: ListAudio[];
	sfx: ListAudio[];
	music: ListAudio[];
	/**
	 * Подложка: непрерывный фон (море, ветер). Отдельно от sfx, потому что у
	 * неё другая громкость и потому что она, как музыка, обязана уступать речи.
	 */
	ambience?: ListAudio[];
	/**
	 * Фоли — дорожка фактуры на отрезок, сгенерированная по самому отрезку.
	 * Отдельный список, а не часть sfx: фоли непрерывен и потому НЕ должен
	 * приглушать музыку (иначе подложка исчезнет на всю серию), а sfx —
	 * событийный и должен.
	 */
	foley?: ListAudio[];
	duck: {gain: number; attackMs: number; releaseMs: number};
	/**
	 * Показывать ли субтитры. Решает КАРТОЧКА ЖАНРА на стороне Python
	 * (`montage.captions_on`), монтаж только слушается: до 2026-09-08 решение
	 * было зашито здесь — 9:16 всегда с субтитрами, 16:9 без них, — и поле
	 * `captions: always` познавательного жанра не работало. Старые листы без
	 * поля читаются как прежде: субтитры только в шортсе.
	 */
	captions?: boolean;
	expected: {segments: number; segmentSeconds: number; tolerance: number};
	shorts: {banner: string; background: string; accent: string};
};

export type PlacedSegment = {
	n: number;
	file: string;
	from: number;
	durationInFrames: number;
};

export type PlacedAudio = {
	id: string;
	file: string;
	volume: number;
	from: number;
	durationInFrames: number;
	text?: string;
	envelope?: EnvelopePoint[];
};

export type Layout = {
	/** Режим: отрезки или кадры под озвучку. */
	mode: 'video' | 'stills';
	/** Кадры, разложенные по времени. Пусто в режиме отрезков. */
	stills: PlacedStill[];
	stillsSettings: StillsSettings;
	fps: number;
	width: number;
	height: number;
	durationInFrames: number;
	segments: PlacedSegment[];
	voice: PlacedAudio[];
	sfx: PlacedAudio[];
	music: PlacedAudio[];
	ambience: PlacedAudio[];
	foley: PlacedAudio[];
	warnings: string[];
	errors: string[];
};

const DEFAULT_FPS = 24;

export const layout = (
	list: EditList,
	media: Record<string, MediaFacts>,
): Layout => {
	const warnings: string[] = [];
	const errors: string[] = [];
	const stillsMode = list.mode === 'stills';
	const stillsSettings: StillsSettings = list.stillsSettings ?? {
		minSeconds: 3,
		tailSeconds: 0.6,
		crossfadeSeconds: 0.4,
		zoom: 1.08,
	};

	for (const file of [
		...list.segments.map((s) => s.file),
		...[...list.voice, ...list.sfx, ...list.music].map((a) => a.file),
	]) {
		if (!media[file]) {
			// Тихий ноль здесь означал бы отрезок нулевой длины в готовом эпизоде —
			// дефект, который заметят уже на просмотре.
			errors.push(`нет метаданных для файла: ${file}`);
		}
	}

	// В режиме кадров опорного видео нет вовсе: fps задаём сами, а размер берём
	// у первого кадра — картинки тоже имеют ширину и высоту.
	const firstStill = stillsMode && list.stills?.length
		? media[list.stills[0].file]
		: undefined;
	const first = stillsMode
		? firstStill
		: list.segments.length
			? media[list.segments[0].file]
			: undefined;
	const fps = stillsMode ? DEFAULT_FPS : (first?.fps ?? DEFAULT_FPS);
	const width = first?.width ?? 0;
	const height = first?.height ?? 0;

	// Расхождение fps лечится ресемплом внутри OffthreadVideo и почти незаметно —
	// предупреждение. Расхождение размеров даёт видимое искажение — отказ
	// (решение 2026-08-01: разнобой внутри эпизода это ошибка конфигурации,
	// падение с внятным сообщением честнее молчаливого апскейла).
	for (const seg of list.segments) {
		const f = media[seg.file];
		if (!f) continue;
		if (f.fps !== fps) {
			warnings.push(
				`${seg.file}: fps ${f.fps} против ${fps} у первого отрезка — ` +
					`кадры будут пересобраны ресемплом`,
			);
		}
		if (f.width !== width || f.height !== height) {
			errors.push(
				`${seg.file}: разрешение ${f.width}x${f.height} против ` +
					`${width}x${height} у первого отрезка`,
			);
		}
	}

	const toFrames = (seconds: number) => Math.round(seconds * fps);

	// Кадры накапливаются по отрезкам, а не округляются из суммы секунд: так
	// стыки не уплывают друг относительно друга на длинном эпизоде.
	const segments: PlacedSegment[] = [];
	const startFrameOf = new Map<number, number>();
	const durationFramesOf = new Map<number, number>();
	let cursor = 0;
	for (const seg of list.segments) {
		const durationInFrames = toFrames(media[seg.file]?.durationInSeconds ?? 0);
		segments.push({n: seg.n, file: seg.file, from: cursor, durationInFrames});
		startFrameOf.set(seg.n, cursor);
		durationFramesOf.set(seg.n, durationInFrames);
		cursor += durationInFrames;
	}
	// Раскладка кадров: длительность каждого диктует его реплика, измеренная
	// parseMedia. В режиме отрезков список пуст и на длительность не влияет.
	const stills: PlacedStill[] = stillsMode
		? placeStills(list.stills ?? [], list.voice, media, stillsSettings, fps)
		: [];

	// В режиме кадров единица привязки — КАДР, а не отрезок: карта стартов
	// заполняется из раскладки кадров. Без этого все реплики встали бы в начало
	// эпизода, потому что карта отрезков в этом режиме пуста.
	if (stillsMode) {
		for (const still of stills) {
			startFrameOf.set(still.n, still.from);
			durationFramesOf.set(still.n, still.durationInFrames);
		}
	}

	const durationInFrames = stillsMode ? stillsDuration(stills) : cursor;

	/**
	 * `warnOverrun` — предупреждать ли о выходе за границу своего отрезка.
	 *
	 * Для речи и SFX выход за границу это ошибка тайминга: звук привязан к
	 * действию в кадре и обязан в него уместиться. Для музыки — штатный случай:
	 * подложка ставится на первый отрезок и играет весь эпизод. Прежний
	 * mix_audio.py предупреждал одинаково для всех трёх списков, то есть ругался
	 * на нормальную работу; предупреждение, срабатывающее всегда, читать
	 * перестают.
	 */
	const place = (entries: ListAudio[], warnOverrun: boolean): PlacedAudio[] =>
		entries.map((entry) => {
			const segmentStart = startFrameOf.get(entry.segment);
			if (segmentStart === undefined) {
				errors.push(`${entry.id}: ссылается на отрезок ${entry.segment}, ` +
					`которого нет в листе`);
			}
			const from = (segmentStart ?? 0) + toFrames(entry.offset);
			const audioFrames = toFrames(media[entry.file]?.durationInSeconds ?? 0);
			const segmentFrames = durationFramesOf.get(entry.segment) ?? 0;
			if (warnOverrun && toFrames(entry.offset) + audioFrames > segmentFrames) {
				warnings.push(
					`${entry.id}: звук длиннее, чем остаток отрезка ` +
						`${entry.segment} — вылезает за его границу`,
				);
			}
			const placed: PlacedAudio = {
				id: entry.id,
				file: entry.file,
				volume: entry.volume,
				from,
				durationInFrames: audioFrames,
			};
			if (entry.text !== undefined) placed.text = entry.text;
			if (entry.envelope !== undefined) placed.envelope = entry.envelope;
			return placed;
		});

	const plannedSeconds = list.expected.segments * list.expected.segmentSeconds;
	const actualSeconds = durationInFrames / fps;
	if (
		plannedSeconds > 0 &&
		Math.abs(actualSeconds - plannedSeconds) >
			plannedSeconds * list.expected.tolerance
	) {
		warnings.push(
			`длительность ${actualSeconds.toFixed(2)}с вне допуска ±5% от ` +
				`плановой ${plannedSeconds}с — проверьте отрезки`,
		);
	}

	return {
		mode: stillsMode ? 'stills' : 'video',
		stills,
		stillsSettings,
		fps,
		width,
		height,
		durationInFrames,
		segments,
		voice: place(list.voice, true),
		sfx: place(list.sfx, true),
		music: place(list.music, false),
		// Подложка длиннее своего отрезка по определению — предупреждать не о чем.
		ambience: place(list.ambience ?? [], false),
		// Фоли не предупреждает о выходе за границу отрезка по той же причине,
		// что музыка: он длиной ровно в отрезок, и округление кадров регулярно
		// даёт лишний кадр — предупреждение срабатывало бы всегда.
		foley: place(list.foley ?? [], false),
		warnings,
		errors,
	};
};
