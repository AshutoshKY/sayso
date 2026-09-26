#import "ExceptionCatch.h"

BOOL LayaTry(void (^block)(void), NSError **error) {
    @try {
        block();
        return YES;
    } @catch (NSException *ex) {
        if (error) {
            *error = [NSError errorWithDomain:@"LayaOpener"
                                         code:1
                                     userInfo:@{NSLocalizedDescriptionKey: ex.reason ?: @"exception"}];
        }
        return NO;
    }
}
