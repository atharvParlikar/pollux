#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
  int data;
  struct Node *next;
} Node;

// Function to add a node at the end
Node *addNode(Node *head, int data) {
  Node *newNode = (Node *)malloc(sizeof(Node));
  newNode->data = data;
  newNode->next = NULL;
  if (head == NULL) {
    return newNode;
  }
  Node *current = head;
  while (current->next != NULL) {
    current = current->next;
  }
  current->next = newNode;
  return head;
}

// Function to print the list
void printList(Node *head) {
  Node *current = head;
  while (current != NULL) {
    printf("%d -> ", current->data);
    current = current->next;
  }
  printf("NULL\n");
}

int main() {
  Node *head = NULL;
  head = addNode(head, 10);
  head = addNode(head, 20);
  head = addNode(head, 30);

  printList(head);
  return 0;
}
