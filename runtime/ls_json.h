/*
  Copyright (c) 2009-2017 Dave Gamble and lsJSON contributors

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
*/

#ifndef lsJSON__h
#define lsJSON__h

#ifdef __cplusplus
extern "C"
{
#endif

#if !defined(__WINDOWS__) && (defined(WIN32) || defined(WIN64) || defined(_MSC_VER) || defined(_WIN32))
#define __WINDOWS__
#endif

#ifdef __WINDOWS__

/* When compiling for windows, we specify a specific calling convention to avoid issues where we are being called from a project with a different default calling convention.  For windows you have 3 define options:

LSJSON_HIDE_SYMBOLS - Define this in the case where you don't want to ever dllexport symbols
LSJSON_EXPORT_SYMBOLS - Define this on library build when you want to dllexport symbols (default)
LSJSON_IMPORT_SYMBOLS - Define this if you want to dllimport symbol

For *nix builds that support visibility attribute, you can define similar behavior by

setting default visibility to hidden by adding
-fvisibility=hidden (for gcc)
or
-xldscope=hidden (for sun cc)
to CFLAGS

then using the LSJSON_API_VISIBILITY flag to "export" the same symbols the way LSJSON_EXPORT_SYMBOLS does

*/

#define LSJSON_CDECL __cdecl
#define LSJSON_STDCALL __stdcall

/* export symbols by default, this is necessary for copy pasting the C and header file */
#if !defined(LSJSON_HIDE_SYMBOLS) && !defined(LSJSON_IMPORT_SYMBOLS) && !defined(LSJSON_EXPORT_SYMBOLS)
#define LSJSON_EXPORT_SYMBOLS
#endif

#if defined(LSJSON_HIDE_SYMBOLS)
#define LSJSON_PUBLIC(type)   type LSJSON_STDCALL
#elif defined(LSJSON_EXPORT_SYMBOLS)
#define LSJSON_PUBLIC(type)   __declspec(dllexport) type LSJSON_STDCALL
#elif defined(LSJSON_IMPORT_SYMBOLS)
#define LSJSON_PUBLIC(type)   __declspec(dllimport) type LSJSON_STDCALL
#endif
#else /* !__WINDOWS__ */
#define LSJSON_CDECL
#define LSJSON_STDCALL

#if (defined(__GNUC__) || defined(__SUNPRO_CC) || defined (__SUNPRO_C)) && defined(LSJSON_API_VISIBILITY)
#define LSJSON_PUBLIC(type)   __attribute__((visibility("default"))) type
#else
#define LSJSON_PUBLIC(type) type
#endif
#endif

/* project version */
#define LSJSON_VERSION_MAJOR 1
#define LSJSON_VERSION_MINOR 7
#define LSJSON_VERSION_PATCH 18

#include <stddef.h>

/* lsJSON Types: */
#define lsJSON_Invalid (0)
#define lsJSON_False  (1 << 0)
#define lsJSON_True   (1 << 1)
#define lsJSON_NULL   (1 << 2)
#define lsJSON_Number (1 << 3)
#define lsJSON_String (1 << 4)
#define lsJSON_Array  (1 << 5)
#define lsJSON_Object (1 << 6)
#define lsJSON_Raw    (1 << 7) /* raw json */

#define lsJSON_IsReference 256
#define lsJSON_StringIsConst 512

/* The lsJSON structure: */
typedef struct lsJSON
{
    /* next/prev allow you to walk array/object chains. Alternatively, use GetArraySize/GetArrayItem/GetObjectItem */
    struct lsJSON *next;
    struct lsJSON *prev;
    /* An array or object item will have a child pointer pointing to a chain of the items in the array/object. */
    struct lsJSON *child;

    /* The type of the item, as above. */
    int type;

    /* The item's string, if type==lsJSON_String  and type == lsJSON_Raw */
    char *valuestring;
    /* writing to valueint is DEPRECATED, use lsJSON_SetNumberValue instead */
    int valueint;
    /* The item's number, if type==lsJSON_Number */
    double valuedouble;

    /* The item's name string, if this item is the child of, or is in the list of subitems of an object. */
    char *string;
} lsJSON;

typedef struct lsJSON_Hooks
{
      /* malloc/free are CDECL on Windows regardless of the default calling convention of the compiler, so ensure the hooks allow passing those functions directly. */
      void *(LSJSON_CDECL *malloc_fn)(size_t sz);
      void (LSJSON_CDECL *free_fn)(void *ptr);
} lsJSON_Hooks;

typedef int lsJSON_bool;

/* Limits how deeply nested arrays/objects can be before lsJSON rejects to parse them.
 * This is to prevent stack overflows. */
#ifndef LSJSON_NESTING_LIMIT
#define LSJSON_NESTING_LIMIT 1000
#endif

/* returns the version of lsJSON as a string */
LSJSON_PUBLIC(const char*) lsJSON_Version(void);

/* Supply malloc, realloc and free functions to lsJSON */
LSJSON_PUBLIC(void) lsJSON_InitHooks(lsJSON_Hooks* hooks);

/* Memory Management: the caller is always responsible to free the results from all variants of lsJSON_Parse (with lsJSON_Delete) and lsJSON_Print (with stdlib free, lsJSON_Hooks.free_fn, or lsJSON_free as appropriate). The exception is lsJSON_PrintPreallocated, where the caller has full responsibility of the buffer. */
/* Supply a block of JSON, and this returns a lsJSON object you can interrogate. */
LSJSON_PUBLIC(lsJSON *) lsJSON_Parse(const char *value);
LSJSON_PUBLIC(lsJSON *) lsJSON_ParseWithLength(const char *value, size_t buffer_length);
/* ParseWithOpts allows you to require (and check) that the JSON is null terminated, and to retrieve the pointer to the final byte parsed. */
/* If you supply a ptr in return_parse_end and parsing fails, then return_parse_end will contain a pointer to the error so will match lsJSON_GetErrorPtr(). */
LSJSON_PUBLIC(lsJSON *) lsJSON_ParseWithOpts(const char *value, const char **return_parse_end, lsJSON_bool require_null_terminated);
LSJSON_PUBLIC(lsJSON *) lsJSON_ParseWithLengthOpts(const char *value, size_t buffer_length, const char **return_parse_end, lsJSON_bool require_null_terminated);

/* Render a lsJSON entity to text for transfer/storage. */
LSJSON_PUBLIC(char *) lsJSON_Print(const lsJSON *item);
/* Render a lsJSON entity to text for transfer/storage without any formatting. */
LSJSON_PUBLIC(char *) lsJSON_PrintUnformatted(const lsJSON *item);
/* Render a lsJSON entity to text using a buffered strategy. prebuffer is a guess at the final size. guessing well reduces reallocation. fmt=0 gives unformatted, =1 gives formatted */
LSJSON_PUBLIC(char *) lsJSON_PrintBuffered(const lsJSON *item, int prebuffer, lsJSON_bool fmt);
/* Render a lsJSON entity to text using a buffer already allocated in memory with given length. Returns 1 on success and 0 on failure. */
/* NOTE: lsJSON is not always 100% accurate in estimating how much memory it will use, so to be safe allocate 5 bytes more than you actually need */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_PrintPreallocated(lsJSON *item, char *buffer, const int length, const lsJSON_bool format);
/* Delete a lsJSON entity and all subentities. */
LSJSON_PUBLIC(void) lsJSON_Delete(lsJSON *item);

/* Returns the number of items in an array (or object). */
LSJSON_PUBLIC(int) lsJSON_GetArraySize(const lsJSON *array);
/* Retrieve item number "index" from array "array". Returns NULL if unsuccessful. */
LSJSON_PUBLIC(lsJSON *) lsJSON_GetArrayItem(const lsJSON *array, int index);
/* Get item "string" from object. Case insensitive. */
LSJSON_PUBLIC(lsJSON *) lsJSON_GetObjectItem(const lsJSON * const object, const char * const string);
LSJSON_PUBLIC(lsJSON *) lsJSON_GetObjectItemCaseSensitive(const lsJSON * const object, const char * const string);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_HasObjectItem(const lsJSON *object, const char *string);
/* For analysing failed parses. This returns a pointer to the parse error. You'll probably need to look a few chars back to make sense of it. Defined when lsJSON_Parse() returns 0. 0 when lsJSON_Parse() succeeds. */
LSJSON_PUBLIC(const char *) lsJSON_GetErrorPtr(void);

/* Check item type and return its value */
LSJSON_PUBLIC(char *) lsJSON_GetStringValue(const lsJSON * const item);
LSJSON_PUBLIC(double) lsJSON_GetNumberValue(const lsJSON * const item);

/* These functions check the type of an item */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsInvalid(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsFalse(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsTrue(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsBool(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsNull(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsNumber(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsString(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsArray(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsObject(const lsJSON * const item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_IsRaw(const lsJSON * const item);

/* These calls create a lsJSON item of the appropriate type. */
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateNull(void);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateTrue(void);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateFalse(void);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateBool(lsJSON_bool boolean);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateNumber(double num);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateString(const char *string);
/* raw json */
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateRaw(const char *raw);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateArray(void);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateObject(void);

/* Create a string where valuestring references a string so
 * it will not be freed by lsJSON_Delete */
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateStringReference(const char *string);
/* Create an object/array that only references it's elements so
 * they will not be freed by lsJSON_Delete */
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateObjectReference(const lsJSON *child);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateArrayReference(const lsJSON *child);

/* These utilities create an Array of count items.
 * The parameter count cannot be greater than the number of elements in the number array, otherwise array access will be out of bounds.*/
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateIntArray(const int *numbers, int count);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateFloatArray(const float *numbers, int count);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateDoubleArray(const double *numbers, int count);
LSJSON_PUBLIC(lsJSON *) lsJSON_CreateStringArray(const char *const *strings, int count);

/* Append item to the specified array/object. */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_AddItemToArray(lsJSON *array, lsJSON *item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_AddItemToObject(lsJSON *object, const char *string, lsJSON *item);
/* Use this when string is definitely const (i.e. a literal, or as good as), and will definitely survive the lsJSON object.
 * WARNING: When this function was used, make sure to always check that (item->type & lsJSON_StringIsConst) is zero before
 * writing to `item->string` */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_AddItemToObjectCS(lsJSON *object, const char *string, lsJSON *item);
/* Append reference to item to the specified array/object. Use this when you want to add an existing lsJSON to a new lsJSON, but don't want to corrupt your existing lsJSON. */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_AddItemReferenceToArray(lsJSON *array, lsJSON *item);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_AddItemReferenceToObject(lsJSON *object, const char *string, lsJSON *item);

/* Remove/Detach items from Arrays/Objects. */
LSJSON_PUBLIC(lsJSON *) lsJSON_DetachItemViaPointer(lsJSON *parent, lsJSON * const item);
LSJSON_PUBLIC(lsJSON *) lsJSON_DetachItemFromArray(lsJSON *array, int which);
LSJSON_PUBLIC(void) lsJSON_DeleteItemFromArray(lsJSON *array, int which);
LSJSON_PUBLIC(lsJSON *) lsJSON_DetachItemFromObject(lsJSON *object, const char *string);
LSJSON_PUBLIC(lsJSON *) lsJSON_DetachItemFromObjectCaseSensitive(lsJSON *object, const char *string);
LSJSON_PUBLIC(void) lsJSON_DeleteItemFromObject(lsJSON *object, const char *string);
LSJSON_PUBLIC(void) lsJSON_DeleteItemFromObjectCaseSensitive(lsJSON *object, const char *string);

/* Update array items. */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_InsertItemInArray(lsJSON *array, int which, lsJSON *newitem); /* Shifts pre-existing items to the right. */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_ReplaceItemViaPointer(lsJSON * const parent, lsJSON * const item, lsJSON * replacement);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_ReplaceItemInArray(lsJSON *array, int which, lsJSON *newitem);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_ReplaceItemInObject(lsJSON *object,const char *string,lsJSON *newitem);
LSJSON_PUBLIC(lsJSON_bool) lsJSON_ReplaceItemInObjectCaseSensitive(lsJSON *object,const char *string,lsJSON *newitem);

/* Duplicate a lsJSON item */
LSJSON_PUBLIC(lsJSON *) lsJSON_Duplicate(const lsJSON *item, lsJSON_bool recurse);
/* Duplicate will create a new, identical lsJSON item to the one you pass, in new memory that will
 * need to be released. With recurse!=0, it will duplicate any children connected to the item.
 * The item->next and ->prev pointers are always zero on return from Duplicate. */
/* Recursively compare two lsJSON items for equality. If either a or b is NULL or invalid, they will be considered unequal.
 * case_sensitive determines if object keys are treated case sensitive (1) or case insensitive (0) */
LSJSON_PUBLIC(lsJSON_bool) lsJSON_Compare(const lsJSON * const a, const lsJSON * const b, const lsJSON_bool case_sensitive);

/* Minify a strings, remove blank characters(such as ' ', '\t', '\r', '\n') from strings.
 * The input pointer json cannot point to a read-only address area, such as a string constant, 
 * but should point to a readable and writable address area. */
LSJSON_PUBLIC(void) lsJSON_Minify(char *json);

/* Helper functions for creating and adding items to an object at the same time.
 * They return the added item or NULL on failure. */
LSJSON_PUBLIC(lsJSON*) lsJSON_AddNullToObject(lsJSON * const object, const char * const name);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddTrueToObject(lsJSON * const object, const char * const name);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddFalseToObject(lsJSON * const object, const char * const name);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddBoolToObject(lsJSON * const object, const char * const name, const lsJSON_bool boolean);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddNumberToObject(lsJSON * const object, const char * const name, const double number);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddStringToObject(lsJSON * const object, const char * const name, const char * const string);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddRawToObject(lsJSON * const object, const char * const name, const char * const raw);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddObjectToObject(lsJSON * const object, const char * const name);
LSJSON_PUBLIC(lsJSON*) lsJSON_AddArrayToObject(lsJSON * const object, const char * const name);

/* When assigning an integer value, it needs to be propagated to valuedouble too. */
#define lsJSON_SetIntValue(object, number) ((object) ? (object)->valueint = (object)->valuedouble = (number) : (number))
/* helper for the lsJSON_SetNumberValue macro */
LSJSON_PUBLIC(double) lsJSON_SetNumberHelper(lsJSON *object, double number);
#define lsJSON_SetNumberValue(object, number) ((object != NULL) ? lsJSON_SetNumberHelper(object, (double)number) : (number))
/* Change the valuestring of a lsJSON_String object, only takes effect when type of object is lsJSON_String */
LSJSON_PUBLIC(char*) lsJSON_SetValuestring(lsJSON *object, const char *valuestring);

/* If the object is not a boolean type this does nothing and returns lsJSON_Invalid else it returns the new type*/
#define lsJSON_SetBoolValue(object, boolValue) ( \
    (object != NULL && ((object)->type & (lsJSON_False|lsJSON_True))) ? \
    (object)->type=((object)->type &(~(lsJSON_False|lsJSON_True)))|((boolValue)?lsJSON_True:lsJSON_False) : \
    lsJSON_Invalid\
)

/* Macro for iterating over an array or object */
#define lsJSON_ArrayForEach(element, array) for(element = (array != NULL) ? (array)->child : NULL; element != NULL; element = element->next)

/* malloc/free objects using the malloc/free functions that have been set with lsJSON_InitHooks */
LSJSON_PUBLIC(void *) lsJSON_malloc(size_t size);
LSJSON_PUBLIC(void) lsJSON_free(void *object);

#ifdef __cplusplus
}
#endif

#endif
