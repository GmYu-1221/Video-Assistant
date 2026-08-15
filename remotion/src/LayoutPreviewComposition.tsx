import React from 'react';
import {SceneLayoutRenderer} from './layout/SceneLayoutRenderer';
import {loadRegisteredFonts} from './fonts/loadFonts';
void loadRegisteredFonts();
export const LayoutPreviewComposition: React.FC<any> = (props) => <SceneLayoutRenderer layout={props.layout} narrative={props.narrative} images={props.images ?? []} mediaBaseUrl={props.media_base_url}/>;
