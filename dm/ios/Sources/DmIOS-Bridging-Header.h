// The C and Objective-C functions Launcher.swift, GameMenu.swift, LauncherSettings.swift
// and DmHostingController.swift call (DmGameMenu.h, DmRotation.h, the screen's rate).
// project.yml points SWIFT_OBJC_BRIDGING_HEADER here.
#import "DmGameMenu.h"
#import "DmRotation.h"
int front_screen_max_fps(void);   // front.h, front_ios.m: the Frame rate row offers 40 and 120 only on a 120 Hz screen (LauncherSettings.swift offeredOptions)
