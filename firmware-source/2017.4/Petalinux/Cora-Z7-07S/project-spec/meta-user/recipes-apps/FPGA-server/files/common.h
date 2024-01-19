// common.h
// macros for cross-platform compilation of Windows and Linux

#ifndef COMMON_H
#define COMMOM_H

#include <stdlib.h>                     // NULL
#include <stdio.h>                      // printf

#ifdef _WINDOWS                         // WINDOWS

// following defines are needed if windows.h is included
// this prevents winsock.h to be included in windows.h which defines the older version of Winsock (1)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif

#include <windows.h>                    // windows default definitions
#include <memory.h>                     // memset
#include <conio.h>                      // kbhit(), getch()

#define THREAD_HANDLE                   HANDLE
#define INVALID_THREAD                  NULL
#define ZEROMEMORY(address, size)       memset(address, 0, size)
#define THREAD_ENTRY(func, param)       DWORD WINAPI func(param)
#define RETURN_FROM_THREAD(exit_code)   return(exit_code)
#define THREAD_JOIN(handle, res, err)   err = pthread_join(handle, &res);
#define SLEEP(ms)                       Sleep(ms)
#define CONIO_INIT
#define CONIO_KBHIT                     kbhit
#define CONIO_GETCH                     _getch
#define CONIO_RESET

// file I/O
#define FILE_HANDLE                     HANDLE
#define FILE_INVALID                    INVALID_HANDLE_VALUE
#define FILE_OPEN_READ(name)            CreateFileA(name,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL)
#define FILE_OPEN_WRITE(name)           CreateFileA(name,GENERIC_WRITE,0,NULL,TRUNCATE_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL)
#define FILE_OPEN_ERROR(hfile)          ((hFile) == INVALID_HANDLE_VALUE)
#define FILE_READ(hfile, buffer, b_size, b_read, ret)       ret = ReadFile(hfile, buffer, b_size, (LPDWORD)&b_read, NULL)
#define FILE_READ_ERROR(ret, b_read)                        ((ret == 0) || (b_read == 0))
#define FILE_WRITE(hfile, buffer, b_size, b_written, ret)   ret = WriteFile(hFile, buffer, bufsize, (LPDWORD)&write, NULL)
#define FILE_WRITE_ERROR(ret, b_written)                    ((ret == 0) || (b_written == 0))
#define FILE_CLOSE(hfile)               CloseHandle(hfile)

// sockets
#ifndef _WINSOCK_DEPRECATED_NO_WARNINGS
#define _WINSOCK_DEPRECATED_NO_WARNINGS
#endif

#include <winsock2.h>                   // windows socket definitions in WS2_32.lib
#include <ws2tcpip.h>                   // winsock 2 definitions
#include <iphlpapi.h>                   // ip helper function, include windock2.h before this

#define CLOSESOCKET(socket)             closesocket(socket)
#define GETSOCKNAME(socket, addr, len)  getsockname(socket, (sockaddr *)addr, (int *)len)
#define ACCEPT(socket, addr, len)       accept(socket, (SOCKADDR *)addr, (int *)len)

#else                                   // LINUX

#include <sys/types.h>
#include <unistd.h>
#include <string.h>                     // memset, strcmp
#include <pthread.h>                    // POSIX threads
#include <errno.h>                      // errno, error codes
#include <time.h>                       // nanosleep

// required additionally for kbhit() and getch()
#include <sys/select.h>
#include <termios.h>            

#define THREAD_HANDLE                   pthread_t    // this is actually thread ID but used as a windows handle
#define INVALID_THREAD                  0
#define ZEROMEMORY(address, size)       memset(address, 0, size)
#define THREAD_ENTRY(func, param)       void * func(param)
#define RETURN_FROM_THREAD(exit_code)   return((void*)((long)exit_code)) // without (long) get warning "-Wint-to-pointer-cast"
#define SLEEP(ms)                       sleep_ms(ms)
#define CONIO_INIT                      conio::init
#define CONIO_KBHIT                     conio::kbhit
#define CONIO_GETCH                     conio::getch
#define CONIO_RESET                     conio::reset

// file I/O
#include <sys/stat.h>                   // open
#include <fcntl.h>                      // O_RDONLY, etc.
#define FILE_HANDLE                     int
#define FILE_INVALID                    0
#define FILE_OPEN_READ(name)            open(filename, O_RDONLY | O_RSYNC)
#define FILE_OPEN_WRITE(name)           open(filename, O_TRUNC | O_WRONLY)
#define FILE_OPEN_ERROR(hfile)          ((hfile) <= 0)
#define FILE_READ(hfile, buffer, b_size, b_read, ret)       b_read = ::read(hfile, buffer, b_size)
#define FILE_READ_ERROR(ret, b_read)                        (b_read <= 0) 
#define FILE_WRITE(hfile, buffer, b_size, b_written, ret)   b_written = ::write(hFile, buffer, bufsize)
#define FILE_WRITE_ERROR(ret, b_written)                    (b_written <= 0)
#define FILE_CLOSE(hfile)               close(hfile)

// sockets
#include <sys/socket.h>
#include <netinet/in.h>                 // struct sockaddr_in
#include <netdb.h>                      // getaddrinfo
#include <arpa/inet.h>                  // inet_ntoa

#define SOCKET                          int
#define INVALID_SOCKET                  -1
#define SOCKET_ERROR                    -1
#define CLOSESOCKET(socket)             close(socket)
#define GETSOCKNAME(socket, addr, len)  getsockname(socket, (sockaddr *)addr, (socklen_t *)len)
#define GETPEERNAME(socket, addr, len)  getpeername(socket, (sockaddr *)addr, (socklen_t *)len)
#define ACCEPT(socket, addr, len)       accept(socket, (sockaddr *)addr, (socklen_t *)len)


#endif

// general macros and includes

#ifdef _DEBUG
#include <assert.h>                     // assert macro
#endif

#endif                                  // COMMOM_H
