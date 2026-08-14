import {registerRoot} from 'remotion';
import {Root} from './Root';
import {loadRegisteredFonts} from './fonts';
void loadRegisteredFonts();
registerRoot(Root);
