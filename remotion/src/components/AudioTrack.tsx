import React from 'react'; import {Audio, staticFile} from 'remotion';
export const AudioTrack: React.FC<{src:string}> = ({src}) => <Audio src={src.startsWith('http')?src:staticFile(src)} volume={0.85}/>;
