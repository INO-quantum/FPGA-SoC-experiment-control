// single linked list template
// created 03/06/2018 by Andi
// compiled with Visual Studio Express 2013 or g++
// tested with Windows 7 and Ubuntu 18.04 LTS
////////////////////////////////////////////////////////////////////////////////////////////////////

// notes: 
// - each entry must declare a private pointer to next entry called 'next'
//   and declare 'friend single_linked_list<class_name>' to allow access to 'next'.
// - another way would be to declare in template: 'struct Tplus { T *entry; Tplus *next; };'
//   and define list as pointer to Tplus; this way next is not part of T but Tplus class;
//   but this needs to allocate/free for each new/deleteed entry the Tplus entry.

#ifndef SINGLE_LINKED_LIST_HEADER
#define SINGLE_LINKED_LIST_HEADER

#ifdef _DEBUG
#include <assert.h>
#endif

template <class T> class single_linked_list {
private:
	T *first;
	T *last;
	int entries;
public:
	single_linked_list();
	~single_linked_list();

	T *get_first(void) { return first; };
	T *get_next(T *entry);
	T *get_last(void) { return last; };

	void append(T *entry); // adds entry at end of list
	void prepend(T *entry); // adds entry at beginning of list
	bool remove(T *entry); // remove entry without deleting
	bool deleteEntry(T *&entry); // remove entry and delte
	void deleteAll(void); // delete all entries

	void merge(single_linked_list<T> *list); // merges lists: append list and set to empty.

	bool is_empty(void) { return (first == NULL); };
	int get_num(void) { return entries; };
	bool is_in_list(T *entry);
    bool is_last(T *entry) { return (entry == last); }; // note: does not check if entry==NULL!
};

template <class T>
single_linked_list<T>::single_linked_list() {
	first = last = NULL;
	entries = 0;
}

template <class T>
single_linked_list<T>::~single_linked_list() {
#ifdef _DEBUG
	assert(first == NULL);							// empty list manually!
	assert(last == NULL);							// empty list manually!
#endif
}

template <class T>
T * single_linked_list<T>::get_next(T *entry) {
	return (entry != NULL) ? entry->next : first;				// if entry==NULL returns first entry
}

template <class T>
bool single_linked_list<T>::is_in_list(T *entry) {
	T *e = first;
	while (e != NULL) {
		if (e == entry) {
			return true;
		}
		e = e->next;
	}
	return false;
}

// add entry at end of list
template <class T>
void single_linked_list<T>::append(T *entry) {
	if (entry != NULL) {
#ifdef _DEBUG
		assert(entry->next == NULL);					// ensure next is NULL
#else
		entry->next = NULL;
#endif
		if (last == NULL) { // empty list
			first = last = entry;
		}
		else {
/*			T *next = list;
			while (next->next != NULL) {
				next = next->next;
			}
			next->next = entry;*/
			last = last->next = entry;
		}
		++entries;
	}
}

// add entry at beginning of list
template <class T>
void single_linked_list<T>::prepend(T *entry) {
	if (entry != NULL) {
#ifdef _DEBUG
		assert(entry->next == NULL);					// ensure next is NULL
#else
		entry->next = NULL;
#endif
		if (first == NULL) { // empty list
			first = last = entry;
		}
		else {
			entry->next = first;
			first = entry;
		}
		++entries;
	}
}

// remove entry form list but does not delete it
// returns true on success, false on error
template <class T>
bool single_linked_list<T>::remove(T *entry) {
	if ((first != NULL) && (entry != NULL)) {
		if (first == entry) { // first entry
			first = entry->next; // might be NULL
			entry->next = NULL;
			--entries;
			if(last == entry) { // empty list
				last = NULL; 
#ifdef _DEBUG
				assert(entries == 0);
				assert(first == NULL);
#endif
			}
			return true;
		}
		else {
			T *next = first;
			while (next->next != NULL) { // find element before entry
				if (next->next == entry) {
					next->next = entry->next;
					entry->next = NULL;
					--entries;
					if(last == entry) { // last entry of list
						last = next;
#ifdef _DEBUG
						assert(next->next == NULL);
#endif
					}
					return true;
				}
				next = next->next;
			}
		}
	}
	return false;
}

// removes entry form list and deletes it.
// returns true on success, false on error
// notes: 
// - entry is NULL after function returns with true
// - if entry is first entry of list, list is updated to entry->next which might be NULL.
template <class T>
bool single_linked_list<T>::deleteEntry(T *&entry) {
	if (remove(entry) == true) {
		delete(entry);
		entry = NULL;				// invalidate entry
		return true;
	}
	//if (entry != NULL) delete(entry);		// try to delete entry even on error. removed since might cause an exception.
	return false;
}

// removes and deletes all entries in list
// list is NULL afterwards
template <class T>
void single_linked_list<T>::deleteAll(void) {
	T *next;
	while (first) {
		next = first;
		first = first->next;
#ifdef _DEBUG
		if(first == NULL) assert(next == last);
#endif
		next->next = NULL;
		delete(next);
	}
	entries = 0;
	last = NULL;
}

// merges lists: append list and set to empty.
template <class T>
void single_linked_list<T>::merge(single_linked_list<T> *list) {
	if (list != NULL) {
		if (first == NULL) { // empty
			first = list->first;
            last = list->last;
            entries = list->entries;
		}
		else { // not empty
			last->next = list->first;
            last = list->last;
            entries += list->entries;
		}
        // empty appended list
        list->first = list->last = NULL;
        list->entries = 0;
	}
}

#endif // SINGLE_LINKED_LIST_HEADER
