/**
 * Разбиение реплики на строки субтитра (спека 2026-08-31 §7).
 *
 * Субтитры только в 9:16. Источник текста — поле `text` реплики из `audio.json`,
 * тайминг — фактическая длительность озвученного файла. Пословной подсветки нет:
 * она требует таймстемпов от TTS или прогона whisper, это отдельная задача.
 *
 * Функции чистые и живут отдельно от компонента, чтобы их можно было проверить
 * тестом без рендера.
 */

/** Предел длины строки. На 1080 в ширину это читается на телефоне. */
export const MAX_LINE = 42;

const PUNCTUATION = /(?<=[.,!?;:—])\s+/;

const packWords = (text: string): string[] => {
	const lines: string[] = [];
	let current = '';
	for (const word of text.split(/\s+/).filter(Boolean)) {
		const candidate = current ? `${current} ${word}` : word;
		if (candidate.length <= MAX_LINE) {
			current = candidate;
			continue;
		}
		if (current) lines.push(current);
		// Слово длиннее строки не режем: обрывок посреди слова читается хуже,
		// чем строка, вылезшая за предел.
		current = word;
	}
	if (current) lines.push(current);
	return lines;
};

export const splitCaption = (text: string): string[] => {
	const trimmed = text.trim();
	if (!trimmed) return [];
	if (trimmed.length <= MAX_LINE) return [trimmed];

	// Сначала пробуем разрезы по знакам препинания: пауза в речи и перевод
	// строки совпадают, читать легче.
	const lines: string[] = [];
	for (const chunk of trimmed.split(PUNCTUATION)) {
		lines.push(...(chunk.length <= MAX_LINE ? [chunk] : packWords(chunk)));
	}
	return lines.filter(Boolean);
};

/** Строка, видимая на кадре `frame` из интервала длиной `durationInFrames`. */
export const visibleLine = (
	lines: string[],
	frame: number,
	durationInFrames: number,
): string => {
	if (lines.length === 0) return '';
	const per = durationInFrames / lines.length;
	const index = Math.min(lines.length - 1, Math.floor(frame / per));
	return lines[Math.max(0, index)];
};
