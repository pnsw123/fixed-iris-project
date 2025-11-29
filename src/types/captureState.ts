export type CaptureState =
    | 'scanning'      // Trying to find face/eye
    | 'guiding'       // Showing "move closer/center/etc"
    | 'readying'      // All green, stability window
    | 'countdown'     // 3..2..1..
    | 'captured';     // Freeze frame, then navigate
