// The tick in front of the chosen entry of a menu (`role="menuitemradio"`). Every entry holds the place, so that the names stand in one line.

import { CheckIcon } from './icons';

export default function MenuTick({ checked }: { checked: boolean }) {
  return <span className="menu-tick">{checked && <CheckIcon size={14} />}</span>;
}
