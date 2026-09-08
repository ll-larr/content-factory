/**
 * `calculateMetadata` обеих композиций: читает факты о медиа и раскладывает
 * монтажный лист в кадры до старта рендера.
 *
 * Выполняется в бандле (и в Studio, и при рендере), поэтому `parseMedia` идёт с
 * ридером по умолчанию и `staticFile()`-ссылками — `nodeReader` тут неприменим.
 */
import {parseMedia} from '@remotion/media-parser';
import {staticFile} from 'remotion';
import {layout} from './metadata';
import {CANVAS_HEIGHT, CANVAS_WIDTH} from './shortsBox';
import type {EditList, Layout, MediaFacts} from './metadata';

export type EpisodeProps = EditList & {layout?: Layout};

// Холст шортса. Не выводится из исходника: 9:16 это сознательная смена формата,
// а не подгонка под то, что отдала модель.
export const SHORTS_WIDTH = CANVAS_WIDTH;
export const SHORTS_HEIGHT = CANVAS_HEIGHT;

// ВСЕ звуковые слои: без фактов о файле его длительность равна нулю, и Remotion
// отказывается рендерить кадр («durationInFrames must be positive»). Слой,
// забытый здесь, ломает рендер целиком — так вскрылись подложка и фоли
// (2026-09-05): фоли отсутствовал в списке с момента появления и молчал только
// потому, что живьём ни разу не запускался.
const audioFiles = (props: EditList) =>
	[
		...props.voice,
		...props.sfx,
		...props.music,
		...(props.ambience ?? []),
		...(props.foley ?? []),
	].map((a) => a.file);

const readFacts = async (
	file: string,
	isVideo: boolean,
): Promise<MediaFacts> => {
	// У звуковых файлов нет ни fps, ни размеров — спрашивать их бессмысленно,
	// а у части контейнеров ещё и приводит к отказу парсера.
	const result = await parseMedia({
		src: staticFile(file),
		acknowledgeRemotionLicense: true,
		fields: isVideo
			? {durationInSeconds: true, fps: true, dimensions: true}
			: {durationInSeconds: true},
	});
	const dimensions = 'dimensions' in result ? result.dimensions : null;
	return {
		durationInSeconds: result.durationInSeconds ?? 0,
		fps: ('fps' in result ? result.fps : null) ?? 0,
		width: dimensions?.width ?? 0,
		height: dimensions?.height ?? 0,
	};
};

export const calculateEpisodeMetadata = async ({
	props,
}: {
	props: EpisodeProps;
}) => {
	const media: Record<string, MediaFacts> = {};
	await Promise.all([
		...props.segments.map(async (s) => {
			media[s.file] = await readFacts(s.file, true);
		}),
		...[...new Set(audioFiles(props))].map(async (file) => {
			media[file] = await readFacts(file, false);
		}),
	]);

	const placed = layout(props, media);

	// Отказ — исключение: рендер, который всё равно даст испорченный эпизод,
	// честнее не начинать. Предупреждения печатаются и не мешают.
	if (placed.errors.length > 0) {
		throw new Error(
			'МОНТАЖ НЕВОЗМОЖЕН:\n' +
				placed.errors.map((e) => `  - ${e}`).join('\n'),
		);
	}
	for (const warning of placed.warnings) {
		console.warn(`ВНИМАНИЕ: ${warning}`);
	}

	const shorts = props.format === '9x16';
	return {
		// Композиция нулевой длины Remotion не примет; пустой лист бывает только
		// в Studio с дефолтными пропсами.
		durationInFrames: Math.max(1, placed.durationInFrames),
		fps: placed.fps,
		width: shorts ? SHORTS_WIDTH : placed.width || SHORTS_HEIGHT,
		height: shorts ? SHORTS_HEIGHT : placed.height || SHORTS_WIDTH,
		props: {...props, layout: placed},
	};
};
