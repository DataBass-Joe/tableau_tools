from .rest_api_base import *

class GroupMethods():
    def __init__(self, rest_api_base: TableauRestApiBase):
        self.rest_api_base = rest_api_base

    def __getattr__(self, attr):
        return getattr(self.rest_api_base, attr)

    def query_groups(self) -> etree.Element:
        self.start_log_block()
        groups = self.query_resource("groups")
        for group in groups:
            # Add to group-name : luid cache
            group_luid = group.get("id")
            group_name = group.get('name')
            self.group_name_luid_cache[group_name] = group_luid
        self.end_log_block()
        return groups

    # # No basic verb for querying a single group, so run a query_groups

    def query_groups_json(self, page_number: Optional[int]=None) -> str:
        """
        :type page_number: int
        :rtype: json
        """
        self.start_log_block()
        groups = self.query_resource_json("groups", page_number=page_number)
        #for group in groups:
        #    # Add to group-name : luid cache
        #    group_luid = group.get(u"id")
        #    group_name = group.get(u'name')
        #    self.group_name_luid_cache[group_name] = group_luid
        self.end_log_block()
        return groups

    def query_group(self, group_name_or_luid: str) -> etree.Element:
        self.start_log_block()
        group = self.query_single_element_from_endpoint('group', group_name_or_luid)
        # Add to group_name : luid cache
        group_luid = group.get("id")
        group_name = group.get('name')
        self.group_name_luid_cache[group_name] = group_luid

        self.end_log_block()
        return group

    # Groups luckily cannot have the same 'pretty name' on one site
    def query_group_luid(self, group_name: str) -> str:
        self.start_log_block()
        if group_name in self.group_name_luid_cache:
            group_luid = self.group_name_luid_cache[group_name]
            self.log('Found group name {} in cache with luid {}'.format(group_name, group_luid))
        else:
            group_luid = self.query_luid_from_name(content_type='group', name=group_name)
            self.group_name_luid_cache[group_name] = group_luid
        self.end_log_block()
        return group_luid

    def query_group_name(self, group_luid: str) -> str:
        self.start_log_block()
        for name, luid in list(self.group_name_luid_cache.items()):
            if luid == group_luid:
                group_name = name
                self.log('Found group name {} in cache with luid {}'.format(group_name, group_luid))
                return group_name
        # If match is found
        group = self.query_single_element_from_endpoint('group', group_luid)
        group_luid = group.get("id")
        group_name = group.get('name')
        self.log('Loading the Group: LUID cache')
        self.group_name_luid_cache[group_name] = group_luid
        self.end_log_block()
        return group_name

    # Returns the LUID of an existing group if one already exists
    def create_group(self, group_name=None, direct_xml_request=None):
        """
        :type group_name: unicode
        :type direct_xml_request: etree.Element
        :rtype: unicode
        """
        self.start_log_block()

        if direct_xml_request is not None:
            tsr = direct_xml_request
        else:
            tsr = etree.Element("tsRequest")
            g = etree.Element("group")
            g.set("name", group_name)
            tsr.append(g)

        url = self.build_api_url("groups")
        try:
            new_group = self.send_add_request(url, tsr)
            self.end_log_block()
            return new_group.findall('.//t:group', self.ns_map)[0].get("id")
        # If the name already exists, a HTTP 409 throws, so just find and return the existing LUID
        except RecoverableHTTPException as e:
            if e.http_code == 409:
                self.log('Group named {} already exists, finding and returning the LUID'.format(group_name))
                self.end_log_block()
                return self.query_group_luid(group_name)

    # Creating a synced ad group is completely different, use this method
    # The luid is only available in the Response header if bg sync. Nothing else is passed this way -- how to expose?
    def create_group_from_ad_group(self, ad_group_name, ad_domain_name, default_site_role='Unlicensed',
                                   sync_as_background=True):
        """
        :type ad_group_name: unicode
        :type ad_domain_name: unicode
        :type default_site_role: bool
        :type sync_as_background:
        :rtype: unicode
        """
        self.start_log_block()
        if default_site_role not in self._site_roles:
            raise InvalidOptionException('"{}" is not an acceptable site role'.format(default_site_role))

        tsr = etree.Element("tsRequest")
        g = etree.Element("group")
        g.set("name", ad_group_name)
        i = etree.Element("import")
        i.set("source", "ActiveDirectory")
        i.set("domainName", ad_domain_name)
        i.set("siteRole", default_site_role)
        g.append(i)
        tsr.append(g)

        url = self.build_api_url("groups/?asJob={}".format(str(sync_as_background).lower()))
        self.log(url)
        response = self.send_add_request(url, tsr)
        # Response is different from immediate to background update. job ID lets you track progress on background
        if sync_as_background is True:
            job = response.findall('.//t:job', self.ns_map)
            self.end_log_block()
            return job[0].get('id')
        if sync_as_background is False:
            self.end_log_block()
            group = response.findall('.//t:group', self.ns_map)
            return group[0].get('id')

    # Take a single user_luid string or a collection of luid_strings
    def add_users_to_group(self, username_or_luid_s: List[str], group_name_or_luid: str) -> etree.Element:
        self.start_log_block()
        group_luid = self.query_group_luid(group_name_or_luid)

        users = self.to_list(username_or_luid_s)
        for user in users:
            user_luid = self.query_user_luid(user)

            tsr = etree.Element("tsRequest")
            u = etree.Element("user")
            u.set("id", user_luid)
            tsr.append(u)

            url = self.build_api_url("groups/{}/users/".format(group_luid))
            try:
                self.log("Adding username ID {} to group ID {}".format(user_luid, group_luid))
                result = self.send_add_request(url, tsr)
                return result
            except RecoverableHTTPException as e:
                self.log("Recoverable HTTP exception {} with Tableau Error Code {}, skipping".format(str(e.http_code), e.tableau_error_code))
        self.end_log_block()

    # Local Authentication update group
    def update_group(self, name_or_luid: str, new_group_name: str) -> etree.Element:
        self.start_log_block()
        group_luid = self.query_group_luid(name_or_luid)

        tsr = etree.Element("tsRequest")
        g = etree.Element("group")
        g.set("name", new_group_name)
        tsr.append(g)

        url = self.build_api_url("groups/{}".format(group_luid))
        response = self.send_update_request(url, tsr)
        self.end_log_block()
        return response

    # AD group sync. Must specify the domain and the default site role for imported users
    def sync_ad_group(self, group_name_or_luid: str, ad_group_name: str, ad_domain: str, default_site_role: str,
                      sync_as_background: Optional[bool] = True) -> str:
        self.start_log_block()
        if sync_as_background not in [True, False]:
            error = "'{}' passed for sync_as_background. Use True or False".format(str(sync_as_background).lower())
            raise InvalidOptionException(error)

        if default_site_role not in self._site_roles:
            raise InvalidOptionException("'{}' is not a valid site role in Tableau".format(default_site_role))
        # Check that the group exists
        self.query_group(group_name_or_luid)
        tsr = etree.Element('tsRequest')
        g = etree.Element('group')
        g.set('name', ad_group_name)
        i = etree.Element('import')
        i.set('source', 'ActiveDirectory')
        i.set('domainName', ad_domain)
        i.set('siteRole', default_site_role)
        g.append(i)
        tsr.append(g)

        group_luid = self.query_group_luid(group_name_or_luid)
        url = self.build_api_url(
            "groups/{}".format(group_luid) + "?asJob={}".format(str(sync_as_background)).lower())
        response = self.send_update_request(url, tsr)
        # Response is different from immediate to background update. job ID lets you track progress on background
        if sync_as_background is True:
            job = response.findall('.//t:job', self.ns_map)
            self.end_log_block()
            return job[0].get('id')
        if sync_as_background is False:
            group = response.findall('.//t:group', self.ns_map)
            self.end_log_block()
            return group[0].get('id')

    def delete_groups(self, group_name_or_luid_s: Union[List[str], str]):
        self.start_log_block()
        groups = self.to_list(group_name_or_luid_s)
        for group_name_or_luid in groups:
            if group_name_or_luid == 'All Users':
                self.log('Cannot delete All Users group, skipping')
                continue
            if self.is_luid(group_name_or_luid):
                group_luid = group_name_or_luid
            else:
                group_luid = self.query_group_luid(group_name_or_luid)
            url = self.build_api_url("groups/{}".format(group_luid))
            self.send_delete_request(url)
        self.end_log_block()

    def remove_users_from_group(self, username_or_luid_s: Union[List[str], str], group_name_or_luid: str):
        self.start_log_block()
        group_name = ""
        if self.is_luid(group_name_or_luid):
            group_luid = group_name_or_luid
        else:
            group_name = group_name_or_luid
            group_luid = self.query_group_name(group_name_or_luid)
        users = self.to_list(username_or_luid_s)
        for user in users:
            username = ""
            if self.is_luid(user):
                user_luid = user
            else:
                username = user
                user_luid = self.query_user_luid(user)
            url = self.build_api_url("groups/{}/users/{}".format(group_luid, user_luid))
            self.log('Removing user {}, id {} from group {}, id {}'.format(username, user_luid, group_name, group_luid))
            self.send_delete_request(url)
        self.end_log_block()

class GroupMethods27(GroupMethods):
    def query_groups(self, name_filter=None, domain_name_filter=None, domain_nickname_filter=None, is_local_filter=None,
                     user_count_filter=None, minimum_site_role_filter=None, sorts=None):
        """
        :type name_filter: UrlFilter
        :type domain_name_filter: UrlFilter
        :type domain_nickname_filter: UrlFilter
        :type is_local_filter: UrlFilter
        :type user_count_filter: UrlFilter
        :type minimum_site_role_filter: UrlFilter
        :type sorts: list[Sort]
        :rtype: etree.Element
        """
        filter_checks = {'name': name_filter, 'domainName': domain_name_filter,
                         'domainNickname': domain_nickname_filter, 'isLocal': is_local_filter,
                         'userCount': user_count_filter, 'minimumSiteRole': minimum_site_role_filter}

        filters = self._check_filter_objects(filter_checks)

        self.start_log_block()
        groups = self.query_resource("groups", filters=filters, sorts=sorts)
        for group in groups:
            # Add to group-name : luid cache
            group_luid = group.get("id")
            group_name = group.get('name')
            self.group_name_luid_cache[group_name] = group_luid
        self.end_log_block()
        return groups

    def query_groups_json(self, name_filter=None, domain_name_filter=None, domain_nickname_filter=None,
                          is_local_filter=None, user_count_filter=None, minimum_site_role_filter=None,
                          sorts=None, page_number=None):
            """
            :type name_filter: UrlFilter
            :type domain_name_filter: UrlFilter
            :type domain_nickname_filter: UrlFilter
            :type is_local_filter: UrlFilter
            :type user_count_filter: UrlFilter
            :type minimum_site_role_filter: UrlFilter
            :type sorts: list[Sort]
            :type page_number: int
            :rtype: etree.Element
            """
            filter_checks = {'name': name_filter, 'domainName': domain_name_filter,
                             'domainNickname': domain_nickname_filter, 'isLocal': is_local_filter,
                             'userCount': user_count_filter, 'minimumSiteRole': minimum_site_role_filter}

            filters = self._check_filter_objects(filter_checks)

            self.start_log_block()
            groups = self.query_resource_json("groups", filters=filters, sorts=sorts, page_number=page_number)
            self.end_log_block()
            return groups

        # # No basic verb for querying a single group, so run a query_groups

    def query_group(self, group_name_or_luid: str) -> etree.Element:
        self.start_log_block()
        group = self.query_single_element_from_endpoint_with_filter('group', group_name_or_luid)
        # Add to group_name : luid cache
        group_luid = group.get("id")
        group_name = group.get('name')
        self.group_name_luid_cache[group_name] = group_luid

        self.end_log_block()
        return group

        # Groups luckily cannot have the same 'pretty name' on one site



class GroupMethods28(GroupMethods27):
    pass

class GroupMethods30(GroupMethods28):
    pass

class GroupMethods31(GroupMethods30):
    pass

class GroupMethods32(GroupMethods31):
    pass

class GroupMethods33(GroupMethods32):
    pass

class GroupMethods34(GroupMethods33):
    pass