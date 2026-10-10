struct lv { int length; char *value; } lv;
int f() {
    int initial = 1000;
    struct lv *lv = malloc(sizeof(*lv));
    lv->length = initial;
    lv->value = malloc(initial);
    free(lv);
    free(lv->value);
    strcpy(buf, var);
}
