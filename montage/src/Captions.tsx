/**
 * Субтитры: одна реплика — одна плашка на свой интервал.
 *
 * Кому они нужны, решает КАРТОЧКА ЖАНРА, а не композиция (поле `captions`
 * листа). Прежнее «только в 9:16» осталось поведением по умолчанию, но у
 * познавательного жанра в карточке стоит `always`: его смотрят без звука чаще
 * повествования, и цифра на экране запоминается лучше произнесённой.
 *
 * Полоса приходит снаружи: у шортса её считает `shortsBox`, у горизонтального
 * эпизода это нижняя треть кадра. Ширина берётся от родителя, а не от холста
 * шортса, — иначе плашка не переезжает между форматами.
 */
import React from 'react';
import {Sequence, useCurrentFrame} from 'remotion';
import {splitCaption, visibleLine} from './captionLines';
import type {Band} from './shortsBox';
import type {PlacedAudio} from './metadata';

const CaptionPlate: React.FC<{
	entry: PlacedAudio;
	band: Band;
	overlay: boolean;
}> = ({entry, band, overlay}) => {
	const frame = useCurrentFrame();
	const lines = splitCaption(entry.text ?? '');
	const line = visibleLine(lines, frame, entry.durationInFrames);
	if (!line) return null;
	return (
		<div
			style={{
				position: 'absolute',
				top: band.top,
				left: 0,
				width: '100%',
				height: band.height,
				display: 'flex',
				alignItems: 'center',
				justifyContent: 'center',
			}}
		>
			<div
				style={{
					maxWidth: '86%',
					textAlign: 'center',
					fontFamily: 'Onest, sans-serif',
					fontWeight: 600,
					fontSize: 56,
					lineHeight: 1.25,
					color: '#FFFFFF',
					// Обводка вместо подложки: кадр под субтитром остаётся виден, а
					// текст читается и на светлом, и на тёмном. Поверх картинки тень
					// плотнее — там под текстом может оказаться что угодно.
					textShadow: overlay
						? '0 0 24px rgba(0,0,0,0.95), 0 2px 8px rgba(0,0,0,0.9)'
						: '0 0 18px rgba(0,0,0,0.85)',
					padding: '0 24px',
				}}
			>
				{line}
			</div>
		</div>
	);
};

export const Captions: React.FC<{
	voice: PlacedAudio[];
	band: Band;
	overlay: boolean;
}> = ({voice, band, overlay}) => (
	<>
		{voice.map((entry) => (
			<Sequence
				key={`c-${entry.id}`}
				from={entry.from}
				durationInFrames={entry.durationInFrames}
			>
				<CaptionPlate entry={entry} band={band} overlay={overlay} />
			</Sequence>
		))}
	</>
);
